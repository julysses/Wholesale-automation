"""Bulk official Collin detail evidence. Discovery only; never verifies a sale/owner."""
import argparse
import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

ORIGIN = 'https://apps2.collincountytx.gov'
PREFIX = ORIGIN + '/ForeclosureNotices/DetailPage/'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected county redirect; inspect before continuing')

class DetailParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.links=[]; self.images=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in ('script','style'): self.hidden+=1
        if tag=='a' and attrs.get('href'): self.links.append(attrs['href'])
        if tag=='img' and attrs.get('alt')=='Scan of Foreclosure Notice': self.images.append(attrs.get('src',''))
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
    def handle_data(self, value):
        if not self.hidden and value.strip(): self.text.append(re.sub(r'\s+',' ',value).strip())

def parse_detail(html, document_id):
    if not re.fullmatch(r'\d{1,30}',document_id): raise ValueError('Invalid document ID')
    p=DetailParser();p.feed(html)
    def section(first,last):
        if first not in p.text and last not in p.text: return []
        start=p.text.index(first)+1;end=p.text.index(last,start);return p.text[start:end]
    prop=section('Property Information','Improvement Information')
    owner=section('Owner Information','Tax Information')
    def value(items,label):
        if not items: return None
        index=items.index(label)
        if index+1>=len(items): raise ValueError('Missing field value')
        return items[index+1]
    pages=[re.fullmatch(r'Page\s*:\s*(\d+) of (\d+)',x) for x in p.text]
    pages=[x for x in pages if x]
    if len(pages)!=1 or int(pages[0][1])!=1 or not 1<=int(pages[0][2])<=100: raise ValueError('Unexpected notice pagination')
    if len(p.images)!=1 or not p.images[0].startswith('data:image/jpeg;base64,'): raise ValueError('Missing first notice image')
    image=base64.b64decode(p.images[0].split(',',1)[1],validate=True)
    if not image.startswith(b'\xff\xd8\xff'): raise ValueError('Invalid notice JPEG')
    cad=[x for x in p.links if re.fullmatch(r'https?://(?:www\.)?collincad\.org/propertysearch\?prop_id=\d+',x)]
    if len(cad)>1: raise ValueError('Ambiguous official appraisal reference')
    result={'document_id':document_id,'source_url':PREFIX+document_id,
        'indexed_property_address':value(prop,'Address'),'indexed_owner_name':value(owner,'Name'),
        'indexed_owner_address':value(owner,'Address'),'indexed_legal_description':value(prop,'Legal Description'),
        'indexed_deed_number':value(prop,'Deed Number'),'cad_reference_url':cad[0] if cad else None,
        'cad_property_id':cad[0].split('=')[-1] if cad else None,
        'county_property_metadata_available':bool(prop and owner and cad),'notice_pages_expected':int(pages[0][2]),
        'notice_pages_captured':[1],'all_notice_pages_captured':int(pages[0][2])==1,
        'all_notice_pages_reviewed':False,'identity_verified':False,'current_status_verified':False,
        'trace_eligible':False,'review_reason':'County detail metadata only. Review notice pages, independent property identity and current sale status.',
        'html_sha256':hashlib.sha256(html.encode()).hexdigest(),'page_1_sha256':hashlib.sha256(image).hexdigest()}
    return result,image

def collect(inventory,output,limit=500):
    source=json.loads(Path(inventory).read_text())
    if source.get('county')!='Collin' or source.get('schema_version')!='1.0': raise ValueError('Use normalized Collin inventory')
    documents=[d for page in source['scans'][0] for d in page['documents']]
    ids=[d['document_id'] for d in documents]
    if len(set(ids))!=len(ids): raise ValueError('Duplicate inventory IDs')
    for d in documents:
        if not re.fullmatch(r'\d{1,30}',d['document_id']) or d['document_url']!=PREFIX+d['document_id']: raise ValueError('Invalid official detail link')
    output=Path(output);output.mkdir(mode=0o700,parents=True,exist_ok=True)
    opener=build_opener(NoRedirect());summary=[]
    for doc in documents[:limit]:
        folder=output/doc['document_id'];folder.mkdir(mode=0o700,exist_ok=True);receipt=folder/'receipt.json'
        try:
            if receipt.exists():
                saved=json.loads(receipt.read_text())
                if saved['document_id']!=doc['document_id'] or saved['source_url']!=doc['document_url']: raise ValueError('Receipt identity mismatch')
                for filename,key in [('detail.html','html_sha256'),('page-1.jpg','page_1_sha256')]:
                    if hashlib.sha256((folder/filename).read_bytes()).hexdigest()!=saved[key]: raise ValueError('Saved evidence hash mismatch')
                summary.append(saved);continue
            with opener.open(Request(doc['document_url'],headers={'User-Agent':'WholesaleOS-public-notice-review/1.0'}),timeout=25) as response:
                data=response.read(5_000_001)
                if len(data)>5_000_000: raise ValueError('Detail exceeds size limit')
                html=data.decode('utf-8-sig')
            saved,image=parse_detail(html,doc['document_id'])
            saved.update({'captured_at':datetime.now(timezone.utc).isoformat(),'filed_date':doc['filed_date'],'auction_date':doc['auction_date']})
            for name,content in [('detail.html',html.encode()),('page-1.jpg',image),('receipt.json',json.dumps(saved,indent=2).encode())]:
                target=folder/name;target.write_bytes(content);target.chmod(0o600)
            summary.append(saved)
        except Exception as exc:
            summary.append({'document_id':doc['document_id'],'error':str(exc),'trace_eligible':False})
        finally:
            (output/'summary.json').write_text(json.dumps(summary,indent=2));(output/'summary.json').chmod(0o600)
        print(json.dumps({'processed':len(summary),'total':min(limit,len(documents)),'errors':sum('error' in x for x in summary)}),flush=True)
        time.sleep(.5)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('inventory');parser.add_argument('output');parser.add_argument('--limit',type=int,default=500);args=parser.parse_args()
    if not 1<=args.limit<=500: parser.error('limit must be 1–500')
    result=collect(args.inventory,args.output,args.limit)
    print(json.dumps({'collected':sum('error' not in r for r in result),'errors':sum('error' in r for r in result),'trace_eligible':0}))
