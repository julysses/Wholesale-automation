import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.collectors.capture_receipt_manifest import build
from pipeline.collectors.extraction_receipt_manifest import build as build_extractions


class CaptureManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / '123'
        self.folder.mkdir()
        self.html = b'<div>synthetic county summary</div>'
        (self.folder / 'detail.html').write_bytes(self.html)
        self.pages = []
        for n in (1, 2):
            data = b'\x89PNG\r\n\x1a\n' + bytes([n])
            (self.folder / f'page-{n}.png').write_bytes(data)
            self.pages.append({'page': n, 'sha256': hashlib.sha256(data).hexdigest()})
        self.receipt = {
            'document_id': '123', 'source_url': 'https://dallas.tx.publicsearch.us/doc/123',
            'html_sha256': hashlib.sha256(self.html).hexdigest(),
            'page_1_sha256': self.pages[0]['sha256'], 'notice_pages_expected': 2,
            'captured_at': '2026-10-13T20:00:00Z', 'image_extension': 'png',
        }
        self.save('summary.json', [{'document_id': '123'}], self.root)
        self.save('receipt.json', self.receipt)
        self.full = {'document_id': '123', 'source_url': self.receipt['source_url'],
                     'expected_pages': 2, 'pages': self.pages}
        self.save('all-pages-capture.json', self.full)

    def save(self, name, value, root=None):
        ((root or self.folder) / name).write_text(json.dumps(value))

    def test_county_bound_receipt_without_verification(self):
        items = build(self.root, 'Dallas')
        self.assertEqual(len(items[0]['pages']), 2)
        self.assertEqual(set(items[0]), {'document_id', 'source_url', 'html_sha256',
                                       'captured_at', 'expected_pages', 'pages'})
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            build(self.root, 'Collin')

    def test_file_tamper_and_incomplete_manifest_rejected(self):
        (self.folder / 'page-2.png').write_bytes(b'\x89PNG\r\n\x1a\nchanged')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build(self.root, 'Dallas')
        self.full['pages'] = self.pages[:1]
        self.save('all-pages-capture.json', self.full)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            build(self.root, 'Dallas')

    def test_duplicate_pages_and_bad_summary_rejected(self):
        self.full['pages'][1]['sha256'] = self.pages[0]['sha256']
        self.save('all-pages-capture.json', self.full)
        with self.assertRaisesRegex(ValueError, 'Duplicate pages'):
            build(self.root, 'Dallas')
        (self.folder / 'detail.html').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Detail hash mismatch'):
            build(self.root, 'Dallas')

    def test_extraction_export_rejects_altered_text_and_verified_claims(self):
        captures = build(self.root, 'Dallas')
        for page in self.pages:
            saved = {'document_id': '123', 'source_url': self.receipt['source_url'],
                     'page': page['page'], 'image_sha256': page['sha256'],
                     'engine': 'test/1', 'text': 'synthetic',
                     'text_sha256': hashlib.sha256(b'synthetic').hexdigest(),
                     'confidence': 90, 'review_required': False, 'verified': False,
                     'trace_eligible': False, 'extracted_at': '2026-10-13T20:00:00Z'}
            self.save(f"page-{page['page']}.json", saved)
        self.assertEqual(len(build_extractions(captures, self.root)), 2)
        saved['text'] = 'changed'
        self.save('page-2.json', saved)
        with self.assertRaisesRegex(ValueError, 'text hash mismatch'):
            build_extractions(captures, self.root)
        saved['text'] = 'synthetic'; saved['verified'] = True
        self.save('page-2.json', saved)
        with self.assertRaisesRegex(ValueError, 'authorization mismatch'):
            build_extractions(captures, self.root)


if __name__ == '__main__':
    unittest.main()
