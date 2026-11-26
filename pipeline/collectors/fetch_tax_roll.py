"""Fetch the currently linked official county ZIP, then build review manifests.
Uses public HTTPS only, bounded downloads, no login/CAPTCHA workarounds.
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
from tax_roll import DALLAS_URL, COLLIN_URL, write_manifests, file_hash

class Links(HTMLParser):
 def __init__(self): super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   for k,v in attrs:
    if k=='href' and v:self.links.append(v)

def checked_url(url,host):
 p=urlsplit(url)
 if p.scheme!='https' or p.hostname!=host or p.username or p.password or p.port not in (None,443): raise ValueError('Unreviewed download host')
 return url

class CountyRedirect(HTTPRedirectHandler):
 def __init__(self,host): self.host=host
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  checked_url(newurl,self.host)
  return super().redirect_request(req,fp,code,msg,headers,newurl)

def discover(html,page,county):
 parser=Links();parser.feed(html);host=urlsplit(page).hostname
 pattern=r'/trwfile\.\d+\.zip$' if county=='Dallas' else r'/delinquent-tax-roll\.zip$'
 candidates={urljoin(page,u) for u in parser.links if re.search(pattern,urlsplit(urljoin(page,u)).path,re.I)}
 if len(candidates)!=1: raise ValueError('Expected exactly one official current roll link')
 return checked_url(candidates.pop(),host)

def collect(county,workspace):
 workspace=Path(workspace);workspace.mkdir(parents=True,exist_ok=False,mode=0o700)
 page=DALLAS_URL if county=='Dallas' else COLLIN_URL;host=urlsplit(page).hostname;opener=build_opener(CountyRedirect(host))
 def get(url): return opener.open(Request(url,headers={'User-Agent':'WholesaleOS county-data collector/1.0','Accept':'*/*'}),timeout=45)
 with get(page) as response:
  html=response.read(2_000_001)
  if len(html)>2_000_000: raise ValueError('Source page too large')
  target=discover(html.decode('utf-8'),page,county)
 archive=workspace/'source.zip';limit=300_000_000
 try:
  with get(target) as response,archive.open('xb') as file:
   archive.chmod(0o600)
   if int(response.headers.get('Content-Length',0))>limit: raise ValueError('Archive too large')
   total=0
   while True:
    block=response.read(1024*1024)
    if not block:break
    total+=len(block)
    if total>limit:raise ValueError('Archive too large')
    file.write(block)
   metadata={'county':county,'source_page':page,'download_url':target,'downloaded_at':datetime.now(timezone.utc).isoformat(),'last_modified':response.headers.get('Last-Modified'),'bytes':total}
  metadata['sha256']=file_hash(archive)
  (workspace/'download.json').write_text(json.dumps(metadata,indent=2))
  return write_manifests(archive,county,workspace/'manifests')
 except Exception:
  (workspace/'FAILED').write_text('No accepted collection. Preserve artifacts for diagnosis; do not submit partial files.\n')
  raise

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--county',choices=['Dallas','Collin'],required=True);p.add_argument('--workspace',required=True);args=p.parse_args()
 try:print(json.dumps(collect(args.county,args.workspace),indent=2))
 except Exception as exc:raise SystemExit('Collection failed; no CRM submission: '+type(exc).__name__)
