import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from pipeline.collectors.dallas_appraisal_batch import address_key, match_archive, INFO_FIELDS, MULTI_FIELDS

def table(headers, records):
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=headers);writer.writeheader()
    for record in records: writer.writerow({key:record.get(key,'') for key in headers})
    return output.getvalue()

class DallasBulkTest(unittest.TestCase):
    def test_situs_units_owner_exclusion_and_ambiguity_remain_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'source.zip'
            base={'ACCOUNT_NUM':'000001','APPRAISAL_YR':'2027','STREET_NUM':'1','FULL_STREET_NAME':'EXAMPLE ROAD',
                  'UNIT_ID':'2A','PROPERTY_CITY':'DALLAS','PROPERTY_ZIPCODE':'75201','OWNER_NAME1':'SYNTHETIC OWNER',
                  'OWNER_ADDRESS_LINE1':'9 WRONG MAILING ST','PHONE_NUM':'not-contact-evidence'}
            account_rows=[base,{**base,'ACCOUNT_NUM':'000002','UNIT_ID':'2B','EXCLUDE_OWNER':'Y'},
                          {**base,'ACCOUNT_NUM':'000003','UNIT_ID':'2C'}, {**base,'ACCOUNT_NUM':'000004','UNIT_ID':'2C'}]
            owners=[{'ACCOUNT_NUM':'000001','APPRAISAL_YR':'2027','OWNER_SEQ_NUM':'1','OWNER_NAME':'SYNTHETIC OWNER','OWNERSHIP_PCT':'100'}]
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('ACCOUNT_INFO.CSV',table(INFO_FIELDS,account_rows));z.writestr('MULTI_OWNER.CSV',table(MULTI_FIELDS,owners))
            records=[{'source_record_id':str(n),'source_url':'https://dallas.tx.publicsearch.us/doc/'+str(n),
                      'raw':{'indexed_address':address}} for n,address in enumerate(['1 EXAMPLE RD #2A, DALLAS, TEXAS, 75201','1 EXAMPLE RD UNIT 2B DALLAS TX 75201','1 EXAMPLE RD UNIT 2C DALLAS TX 75201','DALLAS TEXAS','9 WRONG MAILING ST DALLAS TX 75201'])]
            result=match_archive(archive,records,2027)['notices']
            self.assertEqual(result[0]['appraisal_candidates'][0]['account_id'],'000001')
            self.assertFalse(result[0]['trace_eligible']);self.assertNotIn('PHONE_NUM',str(result))
            self.assertIn('appraisal_owner_excluded',result[1]['holds']);self.assertIsNone(result[1]['appraisal_candidates'][0]['owner_name'])
            self.assertIn('ambiguous_appraisal_accounts',result[2]['holds'])
            self.assertIn('complete_index_address_missing',result[3]['holds'])
            self.assertIn('appraisal_situs_unmatched',result[4]['holds'])
            with self.assertRaises(ValueError): match_archive(archive,records,2026)

    def test_complete_address_required_and_units_not_dropped(self):
        self.assertIsNone(address_key('DALLAS, TEXAS'))
        self.assertNotEqual(address_key('1 EXAMPLE LN UNIT A DALLAS TX 75201'),address_key('1 EXAMPLE LN UNIT B DALLAS TX 75201'))
        self.assertEqual(address_key('1 EXAMPLE ROAD #2A, DALLAS, TEXAS 75201'),address_key('1 EXAMPLE RD UNIT 2A DALLAS TX 75201'))
        self.assertEqual(address_key('1 NORTH CENTRAL EXPRESS WAY #2A DALLAS TEXAS 75201'),address_key('1 N CENTRAL EXPY UNIT 2A DALLAS TX 752011234'))

if __name__=='__main__':unittest.main()
