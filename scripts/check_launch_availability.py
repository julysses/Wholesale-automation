"""Independent, read-only availability check; no CRM or provider credentials."""
import json
import os
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TARGETS = {
    "crm_readiness": "https://wholesale-automation.vercel.app/api/readiness",
    "hilltop_site": "https://hilltophome.co",
    "jays_site": "https://thejaysdallas.com",
}
TIMEOUT_SECONDS = 10
RETRY_DELAYS = (2, 5)  # At most three GETs per target; workflow has a hard timeout.
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}


def _http_result(status):
    return status == 200, "ok" if status == 200 else "http_error", status in TRANSIENT_HTTP


def _network_error(error):
    # Classify only; exception text can include response content or sensitive URLs.
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLError):
        return "tls_error", False
    if isinstance(reason, TimeoutError):
        return "timeout", True
    if isinstance(reason, socket.gaierror):
        return "dns_error", True
    if isinstance(reason, OSError):
        return "connection_error", True
    return "unexpected_error", False


def _attempt(name, url):
    started = monotonic()
    status = None
    try:
        with urlopen(Request(url, headers={"User-Agent": "Hilltop-Launch-Monitor/1.0"}),
                     timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            ok, reason, retryable = _http_result(status)
            if ok and name == "crm_readiness":
                try:
                    value = json.loads(response.read(1024))
                except (ValueError, UnicodeError):
                    ok, reason = False, "invalid_readiness_json"
                else:
                    ok = isinstance(value, dict) and value.get("status") == "ok"
                    reason = "ok" if ok else "readiness_unavailable"
    except HTTPError as error:
        status = error.code
        ok, reason, retryable = _http_result(status)
        error.close()
    except Exception as error:
        ok = False
        reason, retryable = _network_error(error)
    return {
        "ok": ok, "reason": reason, "http_status": status,
        "elapsed_ms": round((monotonic() - started) * 1000),
    }, retryable


def probe(item):
    name, url = item
    attempts = []
    for attempt in range(len(RETRY_DELAYS) + 1):
        result, retryable = _attempt(name, url)
        attempts.append(result)
        if result["ok"] or not retryable or attempt == len(RETRY_DELAYS):
            break
        sleep(RETRY_DELAYS[attempt])
    return name, {"ok": attempts[-1]["ok"], "attempts": attempts}


def report(results):
    print(json.dumps(results, sort_keys=True))
    rows = ["## Production availability", "",
            "| Target | Result | Attempts (reason / HTTP / milliseconds) |",
            "| --- | --- | --- |"]
    for name, result in results.items():
        attempts = result["attempts"]
        outcome = "healthy" if result["ok"] else "FAILED"
        if result["ok"] and len(attempts) > 1:
            outcome = "recovered after retry"
        details = "; ".join(f"{a['reason']} / {a['http_status'] or '-'} / {a['elapsed_ms']}"
                            for a in attempts)
        rows.append(f"| {name} | {outcome} | {details} |")
        if not result["ok"]:
            print(f"::error title=Availability check failed::{name}: "
                  f"{attempts[-1]['reason']} after {len(attempts)} attempt(s)")
        elif len(attempts) > 1:
            print(f"::notice title=Availability recovered::{name}: healthy after "
                  f"{len(attempts)} attempts; see summary for transient failures")
    rows.extend(["", "Read-only GETs. Availability does not verify lead submission or SMS delivery.",
                 "Persistent failures still fail this workflow. Response bodies and exception text are never logged."])
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write("\n".join(rows) + "\n")


def main():
    with ThreadPoolExecutor(max_workers=len(TARGETS)) as pool:
        results = dict(pool.map(probe, TARGETS.items()))
    report(results)
    return 0 if all(result["ok"] for result in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
