"""Bind private OCR output to saved capture receipts for service-only delivery."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def build(captures, root):
    output = []
    seen = set()
    for capture in captures:
        doc = capture['document_id']
        if not isinstance(doc, str) or not re.fullmatch(r'\d{1,30}', doc) or doc in seen:
            raise ValueError('Invalid document identity')
        seen.add(doc)
        if len(capture['pages']) != capture['expected_pages']:
            raise ValueError('Incomplete capture')
        for number, page in enumerate(capture['pages'], 1):
            if page['page'] != number:
                raise ValueError('Invalid page order')
            saved = json.loads((Path(root) / doc / f'page-{number}.json').read_text())
            if (saved['document_id'] != doc or saved['page'] != number
                    or saved['source_url'] != capture['source_url']
                    or saved['image_sha256'] != page['sha256']
                    or saved['verified'] is not False or saved['trace_eligible'] is not False):
                raise ValueError('OCR identity or authorization mismatch')
            text = saved['text']
            if not isinstance(text, str) or len(text.encode()) > 100000 or hashlib.sha256(text.encode()).hexdigest() != saved['text_sha256']:
                raise ValueError('OCR text hash mismatch')
            score = saved['confidence']
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
                raise ValueError('Invalid confidence')
            if saved['review_required'] is not (not text.strip() or score < 85):
                raise ValueError('Quality flag mismatch')
            if not re.fullmatch(r'[a-zA-Z0-9/._-]{1,128}', saved['engine']):
                raise ValueError('Invalid engine')
            output.append({key: saved[key] for key in ['document_id', 'source_url', 'page', 'image_sha256',
                          'engine', 'text', 'text_sha256', 'confidence', 'extracted_at']} |
                          {'html_sha256': capture['html_sha256']})
    if not 1 <= len(output) <= 500:
        raise ValueError('Delivery batch must contain 1–500 pages')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures'); parser.add_argument('ocr_root'); parser.add_argument('output')
    args = parser.parse_args()
    items = build(json.loads(Path(args.captures).read_text()), args.ocr_root)
    target = Path(args.output)
    target.write_text(json.dumps(items)); target.chmod(0o600)
    print(json.dumps({'pages': len(items), 'verification_granted': False}))
