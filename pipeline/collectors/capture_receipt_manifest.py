"""Build a private upload manifest from hash-checked county evidence; no verification grant."""
import argparse
import hashlib
import json
import re
from pathlib import Path

SOURCES = {
    'Collin': ('https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/', 'jpg'),
    'Dallas': ('https://dallas.tx.publicsearch.us/doc/', 'png'),
}

def build(root, county='Collin'):
    if county not in SOURCES: raise ValueError('Unsupported county')
    prefix, extension = SOURCES[county]
    root=Path(root)
    summary=json.loads((root/'summary.json').read_text())
    if not 1<=len(summary)<=500: raise ValueError('Invalid batch size')
    items=[];seen=set()
    for row in summary:
        doc=row['document_id']
        if not re.fullmatch(r'\d{1,30}',doc) or doc in seen: raise ValueError('Invalid document identity')
        seen.add(doc)
        folder=root/doc;receipt=json.loads((folder/'receipt.json').read_text())
        if receipt['document_id']!=doc or receipt['source_url']!=prefix+doc: raise ValueError('Receipt identity mismatch')
        if receipt.get('image_extension', extension)!=extension: raise ValueError('Unexpected image format')
        expected=receipt['notice_pages_expected']
        if type(expected) is not int or not 1<=expected<=100: raise ValueError('Invalid expected pages')
        if hashlib.sha256((folder/'detail.html').read_bytes()).hexdigest()!=receipt['html_sha256']: raise ValueError('Detail hash mismatch')
        pages=[{'page':1,'sha256':receipt['page_1_sha256']}]
        capture=folder/'all-pages-capture.json'
        if capture.exists():
            full=json.loads(capture.read_text())
            if full['document_id']!=doc or full['source_url']!=receipt['source_url'] or full['expected_pages']!=receipt['notice_pages_expected']: raise ValueError('Full capture identity mismatch')
            pages=full['pages']
            if len(pages)!=full['expected_pages'] or pages[0]['sha256']!=receipt['page_1_sha256']: raise ValueError('Full capture incomplete')
        if len({p['sha256'] for p in pages})!=len(pages): raise ValueError('Duplicate pages')
        for n,page in enumerate(pages,1):
            data=(folder/f'page-{n}.{extension}').read_bytes()
            signature=b'\xff\xd8\xff' if extension=='jpg' else b'\x89PNG\r\n\x1a\n'
            if not data.startswith(signature): raise ValueError('Invalid image bytes')
            if page['page']!=n or hashlib.sha256(data).hexdigest()!=page['sha256']: raise ValueError('Page hash mismatch')
        items.append({'document_id':doc,'source_url':receipt['source_url'],'html_sha256':receipt['html_sha256'],'captured_at':receipt['captured_at'],'expected_pages':receipt['notice_pages_expected'],'pages':pages})
    return items

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root');parser.add_argument('output');parser.add_argument('--county',choices=SOURCES,default='Collin');args=parser.parse_args()
    items=build(args.root,args.county);target=Path(args.output);target.write_text(json.dumps(items));target.chmod(0o600)
    print(json.dumps({'documents':len(items),'complete_documents':sum(len(x['pages'])==x['expected_pages'] for x in items),'verification_granted':False}))
