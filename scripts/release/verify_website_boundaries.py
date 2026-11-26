"""Public, non-sending website probes. Never supplies a valid lead/contact."""
import json
from pathlib import Path
import urllib.error
import urllib.request
from uuid import uuid4


def probe(url, expected, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "WholesaleOS-readiness-probe"})
    try:
        response = urllib.request.urlopen(request, timeout=40)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read().decode()
    row = {"url":url,"method":"POST" if payload is not None else "GET","status":response.status,"expected":expected}
    if payload is not None:
        row['response'] = json.loads(body)
    else:
        row['html'] = '<html' in body.lower()
    print(json.dumps(row), flush=True)
    assert response.status == expected, row
    return row


if __name__ == '__main__':
    checks = [probe('https://hilltophome.co/',200),probe('https://thejaysdallas.com/sell',200)]
    # Hilltop forwards empty answers to CRM, where missing required fields must
    # be rejected before persistence. Jays rejects malformed input locally.
    checks.append(probe('https://hilltophome.co/api/get-offer',422,{'request_id':str(uuid4()),'answers':{}}))
    checks.append(probe('https://thejaysdallas.com/api/intake',400,{}))
    target = Path(__file__).resolve().parents[2]/'docs/facebook-release/evidence/2026-10-21-website-boundaries.json'
    target.write_text(json.dumps({'valid_submissions':0,'live_delivery_proven':False,'checks':checks},indent=2)+'\n')
