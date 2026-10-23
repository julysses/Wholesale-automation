"""Bind bulk matching metadata to the original saved county HTML, offline."""
import json
import sys
from pathlib import Path
if __package__:
    from .collin_notice_details import parse_detail
else:
    from collin_notice_details import parse_detail

def verify(root, inventory):
    details = json.loads(Path(inventory).read_text())
    if not isinstance(details, list) or not 1 <= len(details) <= 500:
        raise ValueError('Invalid detail inventory')
    seen = set()
    fields = ('source_url', 'html_sha256', 'indexed_property_address', 'indexed_legal_description',
              'indexed_deed_number', 'cad_reference_url', 'cad_property_id', 'notice_pages_expected')
    for detail in details:
        document_id = detail.get('document_id')
        # The existing parser checks identity before it is used as a path.
        if not isinstance(document_id, str) or not document_id.isdigit() or len(document_id) > 30 or document_id in seen:
            raise ValueError('Invalid or duplicate document identity')
        seen.add(document_id)
        parsed, _ = parse_detail((Path(root) / document_id / 'detail.html').read_bytes().decode('utf-8'), document_id)
        if any(parsed.get(field) != detail.get(field) for field in fields):
            raise ValueError('County detail metadata mismatch')
    return len(details)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: verify_detail_inventory.py captures-root details.json')
    print(json.dumps({'verified_metadata_documents': verify(sys.argv[1], sys.argv[2]), 'trace_eligible': False}))
