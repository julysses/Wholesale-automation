# Lessons

- Pulling first can materially change the implementation target; re-inspect the repo after every successful sync before editing.
- Tests must force a local SQLite `DATABASE_URL`; otherwise a developer `.env` can make unit tests attempt real Supabase/Postgres connections.
- When the project requires Python 3.11 but local `python3` is older, document `python3.11` explicitly and keep Pydantic's annotation backport available for local compatibility.
- Security-sensitive webhooks must fail closed when their verification secret is missing; an unset secret should never silently disable verification in production paths.
- Expensive webhook follow-up work should be scheduled behind a small helper with error logging, so call-result persistence and webhook-related background tasks are not coupled to SMS/email latency.
- Realtime webhook events should preserve provider ordering metadata and reassemble from stored chunks; final payloads can be incomplete even when earlier chunk events had the full conversation.
- Last-resort valuation heuristics should expose their assumptions in notes and use available local signals; a single default price per sqft is too brittle for underwriting.
- A Safari `Load failed` toast during Supabase login can be a DNS-level project-host failure; verify `/api/config`, then test the returned `*.supabase.co` auth host directly before changing app auth logic.
