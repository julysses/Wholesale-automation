# Lessons

- Pulling first can materially change the implementation target; re-inspect the repo after every successful sync before editing.
- Tests must force a local SQLite `DATABASE_URL`; otherwise a developer `.env` can make unit tests attempt real Supabase/Postgres connections.
- When the project requires Python 3.11 but local `python3` is older, document `python3.11` explicitly and keep Pydantic's annotation backport available for local compatibility.
- Security-sensitive webhooks must fail closed when their verification secret is missing; an unset secret should never silently disable verification in production paths.
