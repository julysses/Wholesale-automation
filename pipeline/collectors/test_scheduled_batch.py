import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scheduled_batch import claim, package_completed, validate_upload, PROPSTREAM_HEADERS, RETELL_HEADERS


class ScheduledBatchTests(unittest.TestCase):
    def test_retell_validation_preserves_e164_and_rejects_duplicates_and_bad_metadata(self):
        import csv
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'retell.csv'
            row = dict.fromkeys(RETELL_HEADERS, 'test')
            row.update({'phone number':'+12145551234', 'property_state':'TX', 'property_zip':'75001', 'county':'Dallas'})
            row['metadata'] = json.dumps({key:row[key] for key in ('lead_id','parcel_id','trace_request_id','follow_up_task_id')})
            def save(rows):
                with path.open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=RETELL_HEADERS)
                    writer.writeheader(); writer.writerows(rows)
            save([row])
            self.assertTrue(validate_upload(path,'retell')['format_valid'])
            self.assertFalse(validate_upload(path,'retell')['dispatch_authorized'])
            save([row, row])
            self.assertIn('duplicate_recipient', validate_upload(path,'retell')['errors'][0]['reasons'])
            row['phone number'] = "'+12145551234"
            row['metadata'] = '{}'
            row['owner_name'] = ''
            save([row])
            reasons = validate_upload(path,'retell')['errors'][0]['reasons']
            self.assertIn('invalid_us_e164_phone', reasons)
            self.assertIn('crm_metadata_mismatch', reasons)
            self.assertIn('required_context_missing', reasons)

    def test_propstream_format_and_empty_templates(self):
        import csv
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'propstream.csv'
            with path.open('w', newline='') as f:
                csv.writer(f).writerow(PROPSTREAM_HEADERS)
            result = validate_upload(path,'propstream')
            self.assertTrue(result['format_valid'])
            self.assertTrue(result['empty_template'])
            self.assertFalse(result['dispatch_authorized'])
            with path.open('a', newline='') as f:
                csv.writer(f).writerow(['']*len(PROPSTREAM_HEADERS))
            self.assertFalse(validate_upload(path,'propstream')['format_valid'])
            path.write_text('Phone,Name\n')
            self.assertFalse(validate_upload(path,'retell')['format_valid'])

    def test_source_windows_and_failed_attempts_are_not_repeated(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(claim(root, 'Dallas', 'tax', '2026-10-15'))
            self.assertFalse(claim(root, 'Dallas', 'tax', '2026-10-16'))
            self.assertTrue(claim(root, 'Dallas', 'tax', '2026-10-19'))
            self.assertTrue(claim(root, 'Dallas', 'foreclosure', '2026-10-15'))
            self.assertFalse(claim(root, 'Dallas', 'foreclosure', '2026-10-15'))
            self.assertTrue(claim(root, 'Dallas', 'foreclosure', '2026-10-16'))

    def test_existing_worker_attempt_consumes_week(self):
        with tempfile.TemporaryDirectory() as root:
            legacy = Path(root) / 'old.sqlite'
            with sqlite3.connect(legacy) as db:
                db.execute('CREATE TABLE jobs(county TEXT, day TEXT, state TEXT)')
                db.execute("INSERT INTO jobs VALUES('Collin','2026-10-14','exception')")
            self.assertFalse(claim(Path(root)/'new', 'Collin', 'tax', '2026-10-15', legacy))
            self.assertFalse(claim(Path(root)/'new', 'Collin', 'tax', '2026-10-16'))

    def test_completed_packet_never_becomes_a_new_order_or_campaign(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'input.json'
            row = {'parcel_id':'1','identity':{'property_address':'Test','city':'Dallas','zip':'75001'},
                   'owner_name':'=FORMULA','trace_again':False,'outreach_authorized':False,
                   'current_listing':{'stage':'pending'},'exceptions':['verification_pending'],
                   'contacts':[{'phone':'+12145551234','dnc_status':'listed'},
                               {'phone':'+12145551235','dnc_status':'unknown'},
                               {'phone':'+12145551236','dnc_status':'clear','name':'=FORMULA'}]}
            source.write_text(json.dumps({'processor':'bulk-reconcile/1.0','provider_job_id':'test',
                                          'day':'2026-10-14','items':[row]}))
            folder, receipt = package_completed(source, root, '2026-10-15')
            self.assertEqual(receipt['excluded_phones'], 2)
            self.assertEqual(receipt['held_contacts'], 1)
            self.assertEqual(receipt['new_trace_orders'], 0)
            self.assertEqual(receipt['outreach_ready'], 0)
            self.assertEqual(len((folder/'dialer-ready.csv').read_text().splitlines()), 1)
            self.assertEqual(len((folder/'sms-ready.csv').read_text().splitlines()), 1)
            import csv
            for name, headers in [('propstream-upload.csv', PROPSTREAM_HEADERS), ('retell-call-upload.csv', RETELL_HEADERS)]:
                with (folder/name).open(encoding='utf-8-sig') as stream:
                    self.assertEqual(list(csv.reader(stream)), [headers])
            self.assertEqual(RETELL_HEADERS[0], 'phone number')
            self.assertIn('owner_name', RETELL_HEADERS)
            self.assertIn('property_address', RETELL_HEADERS)
            self.assertIn('metadata', RETELL_HEADERS)
            self.assertIn("'=FORMULA", (folder/'contacts-on-hold.csv').read_text())
            self.assertNotIn('12145551234', (folder/'workbook-input.json').read_text())
            self.assertEqual(package_completed(source, root, '2026-10-15')[0], folder)
            row['trace_again'] = True
            source.write_text(json.dumps({'processor':'bulk-reconcile/1.0','provider_job_id':'test',
                                          'day':'2026-10-14','items':[row]}))
            with self.assertRaises(ValueError):
                package_completed(source, root, '2026-10-15')


if __name__ == '__main__':
    unittest.main()
