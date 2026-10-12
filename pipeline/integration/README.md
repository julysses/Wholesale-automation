# Real database acceptance

Run from the repository root:

```sh
PG_BIN=/path/to/postgresql/bin DENO_BIN=/path/to/deno python3 pipeline/integration/run_local.py
```

Requires PostgreSQL 16+ binaries, OpenSSL, Python 3 and Deno 2.9.6. The runner creates a new temporary cluster, binds only localhost on an available port, generates a one-day TLS certificate, creates a disposable database, runs tests, then stops and removes that cluster even if verification fails. It never uses the normal PostgreSQL data directory or a Supabase project. Fixture passwords are local test values, not operational credentials.

The integration script rejects remote database hosts and any database name other than `wholesale_ingress_test`. It loads only the named migrations into the new database; this is not a migration-replay procedure for an existing project. The separate frozen Deno lock records the integration entrypoint's package workspace.

Evidence covered:

- Actual Deno ingress handler with a restricted database login over TLS.
- Successful payload transaction and durable rows.
- Two independent handler instances contending on the same run lock. The test observes two distinct PostgreSQL backend PIDs waiting simultaneously before releasing the lock; simply using `Promise.all` is insufficient.
- Exact duplicate/lost-ack replay, changed-content conflict, expired retention rejection, disabled-source rejection, and database privilege denial.
- Two actual PostgreSQL sessions reserving tracing spend against the same daily cap; one reservation succeeds, the other is capped, and unknown outcomes retain the hold and deny redispatch. No provider is invoked.
- Two actual PostgreSQL sessions making competing offer decisions at the same version. Exactly one succeeds and one conflicts; only one new event is saved. Replaying the successful approval after revocation cannot restore approval.

Local verification uses PostgreSQL 17. CI runs PostgreSQL 16 on Ubuntu 24.04. This establishes transaction behavior against real PostgreSQL and the actual handler; it does not establish deployed Edge routing, production credentials, collector delivery, signed-in browser workflow, or live provider delivery. Those launch gates remain separate.
