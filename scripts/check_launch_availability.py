"""Independent, read-only availability check; no CRM or provider credentials."""
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

TARGETS = {
    "crm_readiness": "https://wholesale-automation.vercel.app/api/readiness",
    "hilltop_site": "https://hilltophome.co",
    "jays_site": "https://thejaysdallas.com",
}


def probe(item):
    name, url = item
    try:
        with urlopen(Request(url, headers={"User-Agent":"Hilltop-Launch-Monitor/1.0"}), timeout=10) as response:
            if response.status != 200:
                return name, False
            if name == "crm_readiness":
                value = json.loads(response.read(1024))
                return name, isinstance(value, dict) and value.get("status") == "ok"
            return name, True
    except Exception:
        # Never print response bodies, lead data or credentials in a public repo.
        return name, False


def main():
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(probe, TARGETS.items()))
    print(json.dumps(results, sort_keys=True))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
