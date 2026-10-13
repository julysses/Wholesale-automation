import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'collectors'))
from tax_roll import MASTER, receivable_layout, collin, dallas, build, write_manifests, cents
from fetch_tax_roll import discover, checked_url

def fixed(fields,values):return ''.join(str(values.get(k,'')).ljust(n) for k,n in fields)
def archive(files):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  for name,value in files.items():z.writestr(name,value)
 b.seek(0);return zipfile.ZipFile(b)
def collin_fixture(roll='001',amount='10.25'):
 master=fixed(MASTER,{'account':'SYNTHETIC-1','roll':roll,'parcel':'000-123','street':'EXAMPLE ST','number':'123','name1':'Synthetic Owner','city':'MAILING CITY','state':'CA','zip':'90001','amount_due':amount,'total_due':amount,'deferral_start':'01/01/9999','deferral_end':'01/01/9999'})
 ar=fixed(receivable_layout(1),{'account':'SYNTHETIC-1','year':'2025','amount_due':amount,'delinquency_date':'02/01/2026','bankruptcy_date':'01/01/9999','judgment_date':'01/01/9999'})
 return {'AM101026.DAT':master+'\r\n','AR101026.DAT':ar+'\r\n','AS101026.DAT':f'Year\tCount\tAmountDue\r\n2025\t1\t{amount}\r\nALL\t1\t{amount}\r\n'}
def dallas_line(**values):
 r=[' ']*534
 fields={'account':(0,34),'year':(34,38),'unit':(38,42),'parcel':(42,76),'due':(100,108),'balance':(110,121),'owner':(225,265),'mailcity':(385,425),'mailstate':(425,427),'mailzip':(427,439),'roll':(439,440)}
 defaults=dict(account='SYNTHETIC-1',year='2025',unit='0001',parcel='000-123',due='20260131',balance='00000001025',owner='Synthetic Owner',mailcity='NOT SITUS',mailstate='CA',mailzip='90001',roll='R');defaults.update(values)
 for k,v in defaults.items():a,b=fields[k];r[a:b]=str(v).ljust(b-a)
 return ''.join(r)
class TaxTests(unittest.TestCase):
 def test_money(self):
  self.assertEqual(cents('00000001025',True),1025);self.assertEqual(cents('-1.25'),-125)
  for value in ['NaN','1e3','1.255','']:
   with self.assertRaises(ValueError):cents(value)
 def test_collin_reconciliation_and_geography(self):
  with archive(collin_fixture()) as z:asof,records,counts=collin(z)
  self.assertEqual(asof,date(2026,10,10));self.assertEqual(counts['reconciled_balance_cents'],1025)
  r=records[0];self.assertEqual(r['property_address'],'123 EXAMPLE ST');self.assertIsNone(r['city']);self.assertIsNone(r['zip']);self.assertIsNone(r['amount_owed']);self.assertIn('MAILING CITY',r['mailing_address'])
 def test_bad_control_rejected(self):
  f=collin_fixture();f['AS101026.DAT']=f['AS101026.DAT'].replace('10.25','10.26')
  with archive(f) as z,self.assertRaisesRegex(ValueError,'reconcile'):collin(z)
 def test_non_real_excluded(self):
  with archive(collin_fixture(roll='002')) as z:self.assertEqual(collin(z)[1],[])
 def test_malformed_width_rejected(self):
  f=collin_fixture();f['AM101026.DAT']=f['AM101026.DAT'].rstrip()+ '\n'
  with archive(f) as z,self.assertRaises(ValueError):collin(z)
 def test_orphan_transaction_rejected(self):
  f=collin_fixture();f['AR101026.DAT']=f['AR101026.DAT'].replace('SYNTHETIC-1','SYNTHETIC-2')
  with archive(f) as z,self.assertRaisesRegex(ValueError,'Orphan'):collin(z)
 def test_dallas_aggregation_and_duplicate_hold(self):
  f={'flat404.DALLASCOUNTY.20261012.123':dallas_line()+'\n'+dallas_line(unit='0002')+'\n'}
  with archive(f) as z:records=dallas(z)[1]
  self.assertEqual(records[0]['raw']['remaining_levy_cents'],2050);self.assertIsNone(records[0]['property_address']);self.assertIsNone(records[0]['city'])
  f[next(iter(f))]+=dallas_line()+'\n'
  with archive(f) as z:_,records,counts=dallas(z)
  self.assertIsNone(records[0]['raw']['remaining_levy_cents']);self.assertIn('duplicate_tax_row_review',records[0]['raw']['review_flags']);self.assertEqual(counts['duplicate_tax_rows'],1)
 def test_dallas_paid_current_personal_excluded(self):
  f={'flat404.DALLASCOUNTY.20261012.123':'\n'.join([dallas_line(balance='00000000000'),dallas_line(due='20270131'),dallas_line(roll='P')])+'\n'}
  with archive(f) as z:self.assertEqual(dallas(z)[1],[])
 def test_stale_archive_and_private_outputs(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.zip'
   with zipfile.ZipFile(p,'w') as z:
    for k,v in collin_fixture().items():z.writestr(k,v)
   with self.assertRaisesRegex(ValueError,'older'):build(p,'Collin',date(2026,10,21))
   result=write_manifests(p,'Collin',Path(d)/'out',date(2026,10,13));self.assertFalse(result['delivered']);self.assertEqual((Path(d)/'out/batch-0000.json').stat().st_mode&0o777,0o600)
 def test_discovery_rejects_ambiguous_and_untrusted_hosts(self):
  page='https://www.dallascounty.org/departments/tax/tax-roll.php'
  self.assertEqual(discover('<a href="/trwfile.123.zip">Download</a>',page,'Dallas'),'https://www.dallascounty.org/trwfile.123.zip')
  for html in ['<a href="https://evil.invalid/trwfile.123.zip">x</a>','<a href="/trwfile.1.zip">x</a><a href="/trwfile.2.zip">y</a>','no file']:
   with self.assertRaises(ValueError):discover(html,page,'Dallas')
  with self.assertRaises(ValueError):checked_url('https://user:secret@www.dallascounty.org/a','www.dallascounty.org')
if __name__=='__main__':unittest.main()
