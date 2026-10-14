import unittest
from pipeline.collectors.collin_notice_details import parse_detail

SCAN = '<span>Page : 1 of 5</span><img alt="Scan of Foreclosure Notice" src="data:image/jpeg;base64,/9j/">'
METADATA = '<p>Property Information</p><p>Address</p><p>1 TEST ST</p><p>Legal Description</p><p>TEST LOT</p><p>Deed Number</p><p>123</p><p>Improvement Information</p><p>Owner Information</p><p>Name</p><p>SYNTHETIC OWNER</p><p>Address</p><p>2 TEST ST</p><p>Tax Information</p><a href="https://collincad.org/propertysearch?prop_id=123">CAD</a>'

class DetailTest(unittest.TestCase):
    def test_scan_without_property_metadata_is_retained_but_not_verified(self):
        receipt, image = parse_detail(SCAN, '123')
        self.assertEqual(image, b'\xff\xd8\xff')
        self.assertEqual(receipt['notice_pages_expected'], 5)
        self.assertIsNone(receipt['cad_property_id'])
        self.assertIsNone(receipt['indexed_owner_name'])
        for key in ['trace_eligible','all_notice_pages_reviewed','all_notice_pages_captured','identity_verified','current_status_verified','county_property_metadata_available']:
            self.assertFalse(receipt[key])

    def test_metadata_does_not_certify_identity(self):
        receipt, _ = parse_detail(METADATA+SCAN, '123')
        self.assertEqual(receipt['indexed_owner_name'], 'SYNTHETIC OWNER')
        self.assertTrue(receipt['county_property_metadata_available'])
        self.assertFalse(receipt['identity_verified'])

    def test_invalid_evidence_rejected(self):
        for html in [METADATA, SCAN.replace('/9j/', 'bad'), SCAN.replace('1 of 5','2 of 5'), SCAN+SCAN, METADATA+METADATA+SCAN, '<p>Property Information</p>'+SCAN]:
            with self.subTest(html=html), self.assertRaises((ValueError, IndexError)):
                parse_detail(html, '123')
        with self.assertRaises(ValueError): parse_detail(SCAN, '../other')

if __name__ == '__main__': unittest.main()
