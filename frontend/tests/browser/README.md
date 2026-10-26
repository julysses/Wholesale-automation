# Acquisition review browser fixture

From `frontend`, run:

```sh
./node_modules/.bin/vite --config tests/browser/vite.config.ts
```

Open `http://127.0.0.1:5179/tests/browser/acquisition-review.html`.

This renders the real review component and stylesheet, while replacing only the API module with a synthetic, in-memory adapter. No user session, Supabase connection, environment file, provider or real mutation is used. The server binds localhost, has no API proxy, and fails on unhandled mock paths. Do not use this config for deployment or production acceptance. The normal Vite build still uses the normal entrypoint and API module.

Repeatable checks:

1. Select Hilltop local QA and open the proposal.
2. Verify address, exact revision, three cases and financial units; unknown equity must remain Unknown.
3. Select Approve amount. Recording stays disabled until the decision note, seven diligence notes and acknowledgment are supplied.
4. Record the synthetic decision; verify confirmation, approved queue status and revocation action.
5. Inspect a 375px mobile viewport and restore the normal viewport afterward.
6. Check browser console errors. Reloading discards all fixture decisions.

The fixture validates browser presentation and interaction only. Session/RLS, real API persistence, provider integration and production cutover require separate acceptance tests.
