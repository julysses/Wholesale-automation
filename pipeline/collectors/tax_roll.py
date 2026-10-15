"""County-published tax snapshots -> bounded review manifests; no network, CRM or outreach.

Read the official ZIP in place (never extract archive paths). Retain the original
outside Git. Monetary reconciliation uses integer cents, not binary floats.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import uuid
import zipfile

DALLAS_URL = 'https://www.dallascounty.org/departments/tax/tax-roll.php'
COLLIN_URL = 'https://www.collincountytx.gov/Tax-Assessor/property-taxes'
MASTER = [('account',30),('sptb',3),('roll',3),('legal',124),('acres',13),('parcel',30),('street',25),('number',10),('sqft',6),('lot',6),('built',4),('loan',10),('map',30),('mapsco',20),('appraisal_map',20),('name1',50),('name2',50),('address1',50),('address2',50),('city',50),('state',20),('zip',18),('deferral_start',10),('deferral_end',10),('volume',6),('page',6),('deed_date',10),('exemptions',15),('delinquency_date',10),('tax_units',30),('nonbilled_units',50),('land',10),('improvements',11),('value',11),('exemption_value',10),('levy',12),('amount_due',12),('total_due',12),('ownership',13)]
def receivable_layout(version):
 return [('account',30),('year',4),('tax_unit',3 if version==1 else 4),('type',3),('sequence',2 if version==1 else 3),('value',11),('exemptions',11),('levy',11),('amount_due',12),('delinquency_date',10),('attorney_date',10),('judgment_date',10),('suit',18),('suit_date',10),('bankruptcy',18),('bankruptcy_date',10),('status',15),('sequence_type',2),('installment',1),('installment_type',3),('installment_start',10),('installment_end',10),('installment_paid',10)]

def split(line, fields):
 out={}; offset=0
 for name,size in fields: out[name]=line[offset:offset+size].strip(); offset+=size
 if len(line)!=offset: raise ValueError('Unexpected fixed-width record length')
 return out

def cents(value, implied=False):
 pattern=r'-?\d+' if implied else r'-?\d+\.\d{2}'
 if not re.fullmatch(pattern,value.strip()): raise ValueError('Invalid monetary field')
 return int(value) if implied else int(Decimal(value)*100)

def parsed_date(value, fmt):
 if value.strip() in ('','00000000','01/01/9999'): return None
 return datetime.strptime(value,fmt).date()

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def file_hash(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return h.hexdigest()

def base_record(account,url):
 return dict(source_record_id=account,case_number=None,property_address=None,unit=None,city=None,parcel_id=None,owner_name=None,mailing_address=None,filed_date=None,auction_date=None,state='TX',zip=None,amount_owed=None,amount_type='unknown',source_url=url,raw={})

def lines(z,name):
 # UTF-8 characters, not byte offsets: five accented names in the observed
 # Collin master add one byte while preserving the 950-character layout.
 with z.open(name) as f:
  for line in io.TextIOWrapper(f,encoding='utf-8-sig',errors='strict',newline=''):
   yield line.rstrip('\r\n')

def validate_zip(z):
 members=z.infolist()
 if len(members)>30 or sum(x.file_size for x in members)>4_000_000_000: raise ValueError('Archive exceeds reviewed bounds')
 if len({x.filename for x in members})!=len(members): raise ValueError('Duplicate archive members')
 if any(x.flag_bits&1 for x in members): raise ValueError('Encrypted archive unsupported')

def collin(z):
 names=z.namelist()
 master=[n for n in names if re.fullmatch(r'AM\d{6}\.DAT',n)]
 if len(master)!=1: raise ValueError('Expected one Collin account master')
 stamp=master[0][2:8]; asof=datetime.strptime(stamp,'%m%d%y').date()
 ar,control='AR'+stamp+'.DAT','AS'+stamp+'.DAT'
 if ar not in names or control not in names: raise ValueError('Missing matching transaction/control file')
 accounts={}; totals=Counter(); flags=defaultdict(set); oldest={}; counts=Counter(); year_amounts=Counter(); year_counts=Counter()
 for line in lines(z,master[0]):
  fields=MASTER+([('mh_label',30),('mh_model',30),('mh_serial',30)] if len(line)==950 else [])
  row=split(line,fields)
  if not row['account'] or row['account'] in accounts: raise ValueError('Missing or duplicate master account')
  accounts[row['account']]=row; counts['master_rows']+=1
 for line in lines(z,ar):
  if len(line) not in (224,226): raise ValueError('Unknown Collin transaction width')
  row=split(line,receivable_layout(1 if len(line)==224 else 2)); account=row['account']
  if account not in accounts: raise ValueError('Orphan transaction account')
  amount=cents(row['amount_due']); totals[account]+=amount; year_amounts[row['year']]+=amount; year_counts[row['year']]+=1; counts['transaction_rows']+=1
  due=parsed_date(row['delinquency_date'],'%m/%d/%Y')
  if amount>0:
   if due is None or due>asof: flags[account].add('unverified_delinquency_date')
   else: oldest[account]=min(oldest.get(account,due),due)
   if row['bankruptcy'] or parsed_date(row['bankruptcy_date'],'%m/%d/%Y'): flags[account].add('bankruptcy_review')
   if row['suit'] or parsed_date(row['judgment_date'],'%m/%d/%Y'): flags[account].add('legal_proceeding_review')
   if row['sequence_type'] not in ('','0','00') or row['installment']=='Y' or row['status']: flags[account].add('payment_status_review')
 controls=list(lines(z,control)); expected={}
 if not controls or controls[0]!='Year\tCount\tAmountDue': raise ValueError('Unexpected control layout')
 for line in controls[1:]:
  if not line: continue
  year,count,amount=line.split('\t')
  if year in expected: raise ValueError('Duplicate control year')
  expected[year]=(int(count),cents(amount))
 actual={year:(year_counts[year],year_amounts[year]) for year in year_counts}
 actual['ALL']=(counts['transaction_rows'],sum(totals.values()))
 if expected!=actual: raise ValueError('Transaction counts or amounts do not reconcile to county control')
 records=[]
 for account,row in sorted(accounts.items()):
  if cents(row['amount_due'])!=totals[account] or cents(row['total_due'])!=totals[account]: raise ValueError('Account amounts do not reconcile to transactions')
  if row['roll']!='001': counts['excluded_non_real_roll']+=1; continue
  if totals[account]<=0: counts['excluded_nonpositive_balance']+=1; continue
  start=parsed_date(row['deferral_start'],'%m/%d/%Y');end=parsed_date(row['deferral_end'],'%m/%d/%Y')
  if start and start<=asof and (end is None or end>=asof): flags[account].add('active_deferral_review')
  record=base_record(account,COLLIN_URL)
  record.update(parcel_id=row['parcel'] or None,property_address=' '.join(x for x in (row['number'],row['street']) if x) or None,owner_name=' '.join(x for x in (row['name1'],row['name2']) if x) or None,mailing_address=', '.join(row[k] for k in ('address1','address2','city','state','zip') if row[k]) or None)
  # Mailing city/state/ZIP are never promoted to property geography. No payoff
  # quote or verified current balance is inferred from an older weekly roll.
  record['raw']={'tax_account':account,'snapshot_date':asof.isoformat(),'snapshot_balance_cents':totals[account],'earliest_delinquency_date':oldest[account].isoformat() if account in oldest else None,'roll_code':row['roll'],'review_flags':','.join(sorted(flags[account])) or 'verify_current_account_status','identity_verified':False,'snapshot_only':True}
  records.append(record)
 counts['candidate_accounts']=len(records); counts['reconciled_balance_cents']=sum(totals.values())
 return asof,records,dict(counts)

def dallas(z):
 names=z.namelist(); files=[n for n in names if re.search(r'(^|/)flat404\.DALLASCOUNTY\.\d{8}\.\d+$',n)]
 if len(files)!=1: raise ValueError('Expected one Dallas tax roll')
 name=files[0];stamp=re.search(r'DALLASCOUNTY\.(\d{8})\.',name)[1];asof=datetime.strptime(stamp,'%Y%m%d').date()
 counts=Counter();accounts={}
 for line in lines(z,name):
  counts['source_rows']+=1
  if len(line)!=534: raise ValueError('Unexpected Dallas record width')
  if line[439]!='R': counts['excluded_non_real_roll_rows']+=1; continue
  balance=cents(line[110:121],True)
  if balance<=0: counts['excluded_nonpositive_rows']+=1;continue
  due=parsed_date(line[100:108],'%Y%m%d')
  if due is None or due>=asof: counts['excluded_not_past_due_rows']+=1;continue
  account=line[:34].strip();parcel=line[42:76].strip();year=line[34:38];unit=line[38:42]
  if not account or not re.fullmatch(r'\d{4}',year) or not unit.strip(): raise ValueError('Invalid tax identity')
  owner=line[225:265].strip();mail=', '.join(line[a:b].strip() for a,b in [(265,305),(305,345),(345,385),(385,425),(425,427),(427,439)] if line[a:b].strip())
  if account not in accounts:
   record=base_record(account,DALLAS_URL);record.update(parcel_id=parcel or None,owner_name=owner or None,mailing_address=mail or None)
   accounts[account]={'record':record,'levy':0,'rows':0,'keys':set(),'flags':set(),'oldest':due}
  saved=accounts[account];key=(year,unit)
  # Duplicate tax keys may be split/supplemental rows. Preserve an explicit
  # review hold and withhold the account aggregate rather than double-count.
  if key in saved['keys']:
   saved['flags'].add('duplicate_tax_row_review');saved['rows']+=1;counts['duplicate_tax_rows']+=1;continue
  saved['keys'].add(key)
  if (saved['record']['parcel_id'],saved['record']['owner_name'],saved['record']['mailing_address'])!=(parcel or None,owner or None,mail or None): saved['flags'].add('identity_conflict_review')
  saved['levy']+=balance;saved['rows']+=1;saved['oldest']=min(saved['oldest'],due)
  if line[218:219]=='D': saved['flags'].add('deferral_review')
  if line[162:163].strip() or line[163:203].strip(): saved['flags'].add('bankruptcy_review')
  if line[121:122].strip() or line[122:162].strip(): saved['flags'].add('legal_proceeding_review')
  if line[220:221].strip() or line[488:489]=='Y': saved['flags'].add('payment_plan_review')
 records=[]
 for account,saved in sorted(accounts.items()):
  r=saved['record'];r['raw']={'tax_account':account,'snapshot_date':asof.isoformat(),'remaining_levy_cents':None if 'duplicate_tax_row_review' in saved['flags'] else saved['levy'],'tax_rows':saved['rows'],'earliest_due_date':saved['oldest'].isoformat(),'roll_code':'R','review_flags':','.join(sorted(saved['flags'])) or 'verify_current_account_status','identity_verified':False,'snapshot_only':True,'situs_missing':True};records.append(r)
 counts['candidate_accounts']=len(records)
 return asof,records,dict(counts)

def build(archive,county,today=None):
 today=today or datetime.now().astimezone().date()
 with zipfile.ZipFile(archive) as z:
  validate_zip(z);asof,records,counts=(dallas if county=='Dallas' else collin)(z)
 if not 0<=(today-asof).days<=10: raise ValueError('Snapshot is future dated or older than ten days')
 return asof,records,counts

def write_manifests(archive,county,output,today=None):
 from zoneinfo import ZoneInfo
 today=today or datetime.now(ZoneInfo('America/Chicago')).date()
 asof,records,counts=build(archive,county,today)
 output=Path(output);output.mkdir(parents=True,exist_ok=False,mode=0o700)
 run=str(uuid.uuid4());pulled=datetime.now(timezone.utc).isoformat();batches=max(1,(len(records)+499)//500);source_hash=file_hash(archive)
 receipt={'run_id':run,'county':county,'snapshot_date':asof.isoformat(),'archive_sha256':source_hash,'counts':counts,'batches':batches,'coverage_complete':False,'delivered':False,'reason':'Archive parsed; current account and county/property identity require review. No verified new opportunities or outreach eligibility implied.'}
 for i in range(batches):
  rows=records[i*500:(i+1)*500]
  payload={'schema_version':'1.0','source_key':f'tx-{county.lower()}-tax_delinquent','run_id':run,'scheduled_for':today.isoformat(),'pulled_at':pulled,'source':{'state':'TX','county':county,'jurisdiction':county+' County','list_type':'tax_delinquent','source_url':DALLAS_URL if county=='Dallas' else COLLIN_URL},'status':'partial','status_reason':receipt['reason'],'lookback_days':(today-asof).days+1,'window_start':asof.isoformat(),'window_end':today.isoformat(),'coverage_complete':False,'source_as_of':asof.isoformat(),'records_sha256':digest(rows),'records':rows,'batch_index':i,'batch_count':batches}
  data=canonical(payload)
  if len(data.encode())>2*1024*1024: raise ValueError('Batch exceeds ingress limit')
  path=output/f'batch-{i:04d}.json';path.write_text(data);path.chmod(0o600)
 (output/'receipt.json').write_text(json.dumps(receipt,indent=2));(output/'receipt.json').chmod(0o600)
 return receipt

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--county',choices=['Dallas','Collin'],required=True);parser.add_argument('--archive',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 try: print(json.dumps(write_manifests(args.archive,args.county,args.output),indent=2))
 except (ValueError,UnicodeError,zipfile.BadZipFile,KeyError) as exc: raise SystemExit(f'Tax collection failed; no CRM submission: {exc}')
