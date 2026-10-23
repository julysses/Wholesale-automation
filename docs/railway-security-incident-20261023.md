# Railway credential incident — 2026-10-23

## Status

The user disabled the April Anthropic key; its Claude console record and success notification were independently verified as Disabled. No replacement key has been created or installed. No deployment, migration, outreach, or scheduler changes made. Other credentials remain unresolved; incident is not yet contained.

### Follow-up after user reported disabled

- Verified `wholesale_automation` / `apikey_01GkYe6foE35RfAXqcGxniVk` displays Disabled. No API request using the old key was made; evidence is provider-console status.
- Opened replacement-key form for user handoff: proposed name `wholesale-railway-recovery-20261023`, Default workspace, linked to current user. UI defaults to 30-day expiry (November 22, 2026). Nothing submitted or typed. User must complete credential creation and preserve the one-time secret outside chat.
- Supabase production has existing modern default publishable and secret keys; legacy tab still exposes Disable JWT-based API keys. No disable performed: both legacy anon and service-role consumers require migration before that action. Existing default secret's exposure/usage history is not yet known.
- Production checkout fast-forwarded from `19c117a` to `a898151`, branch `codex/retell-sms-production`. Current railway.toml starts uvicorn only. Service-role consumers found in `web/app.py`, `web/api/webhooks.py`, and `web/api/buyers_api.py`; broader dependency audit remains pending.
- Attempted sanitized parsing of Railway DATABASE_URL could not identify the host. Earlier Postgres scheme observation stands, but exact database mapping is still unverified. No raw value persisted.

User requested remediation of Railway's October 21 security incident and signed into Railway, Supabase, and the Claude API console. Official source: https://blog.railway.com/p/preliminary-report-october-security-incident . Treat all sensitive credentials stored before the incident as potentially exposed; present-day variable inventory is not proof of historical scope.

## Verified inventory (production environments only)

### Latest handoff: replacement saved, not deployed

- User reports replacement Anthropic key created and saved via Railway Submit. Form is closed. Claude one-time display confirmed creation and expiry **December 31, 2026, 2:00 PM CST**, overriding the earlier form default. Do not copy its secret into logs or source. Exact Railway/new-key matching and runtime authentication remain unverified.
- Railway connector now works with `link_6adba03c016c819195522e805ef1ad51`. The other listed connection repeatedly requests authentication; use the working connection for this verified project.
- `get_staged_changes` identifies patch `4aaefe75-c577-499d-ae21-681491c57a26`, created April 22, updated October 23, status STAGED, two variable changes: ANTHROPIC_API_KEY and SUPABASE_SERVICE_ROLE_KEY. No other staged configuration change. Do not accept this whole patch without addressing the privileged key addition.
- `get_service_config` confirms the live variable inventory has ANTHROPIC_API_KEY but **does not have SUPABASE_SERVICE_ROLE_KEY**. Earlier browser inventory included pending state. Treat the pending service-role secret as potentially exposed storage, but do not describe it as a currently deployed service credential.
- Live Railway source branch is `claude/ai-wholesaling-agency-KkDF1`, not the local launch-prep or retell branch. UI config-as-code points to commit `ad70c7c29d618efe3aad848a386ca1779f0e7b8f`. Start command is uvicorn; active deployment remains `bf158634-88aa-4a64-80aa-0e7f6c8bce7d`. No deployment performed.
- Recommended immediate action: discard only the pre-existing pending service-role addition, preserve the new Anthropic value, re-read staged diff and obtain explicit deployment approval as required by Railway accept-deploy. This avoids introducing unplanned database privileges. Preserve existing live database/anon settings.
- Browser automatic approval review blocked clicking Done on Claude's one-time key display until secure retention is confirmed. Left it open; ask user to save the key securely and close it. Do not bypass the block or reproduce the key.
- Railway outage banner now says a fix is out and monitoring is underway. This is not deployment or credential verification.

- Railway workspace: julysses's Projects, `d4ee9a0a-3bb5-47cc-a255-3e02cf5dcfef`.
- `practical-youthfulness`, project `8a8dc45c-5c24-4a50-877f-1cd48caf1577`, service `web` (`9768c6aa-f30f-49d6-9be9-5b4a80fd35b4`), environment `5382d87c-b87a-4137-b704-e380541586d4`: 22 saved variables, including ANTHROPIC_API_KEY, DATABASE_URL, REALTY_API_KEY, SUPABASE_SERVICE_ROLE_KEY. Public VITE_SUPABASE_URL points to production `dvzhzlipbwzzcliujzyz`. DATABASE_URL begins with a Postgres scheme; password/host dependency mapping remains unfinished. Values were not saved to this document.
- Anthropic: Railway key's visible prefix matches `wholesale_automation`, created April 21, 2026, key record `apikey_01GkYe6foE35RfAXqcGxniVk`, Default workspace, legacy/unlinked, last used 30+ days ago. Do not confuse with `Wholesale_automation_july2026`. The April key menu exposes Disable API key and Delete API key. No disable submitted. Exact full-value equality was not checked.
- Claude dashboard showed $0 current-month spend and zero seven-day token volume. This is not a complete activity audit or proof of no compromise.
- `airy-abundance`, project `46c7f57c-bc90-4413-a04d-ce09461f062f`, service `dd8f967a-100e-452e-9dcb-1d70c0934409`, environment `222a7d81-c9ac-4760-83a5-9e5f1c81c6b0`: two saved shared variables, OPENAI_API_KEY and GEMINI_API_KEY. Provider identities, usage, and revocation pending.
- `pure-recreation`, `mellow-luck`, and `refreshing-youth`: inspected service Variables pages showed source suggestions and Railway-generated variables, with no saved custom masked rows observed. Suggestions are not evidence of stored credentials. Alternate environments, unused shared variables, registry credentials, and historical exposure remain to inspect.

## Production constraints

- Railway web currently has TWO PRE-EXISTING STAGED CHANGES. Do not apply them blindly when replacing credentials or redeploying.
- Railway active deployment observed: `bf158634-88aa-4a64-80aa-0e7f6c8bce7d`, message “Handle transient availability failures and preserve current production release”.
- Railway displays an active platform outage banner; verify status before a deployment.
- Supabase production dashboard reports Healthy, last backup six hours ago, 594 requests / 99.5% success over 24 hours, two Postgres errors. No security clearance inferred from these summaries.
- This checkout is `codex/dallas-collin-launch-prep`; newer production runtime work is in sibling `wholesale-sms-production`, branch `codex/retell-sms-production`. Inspect exact live source/config before code changes. Do not deploy this older branch as incident recovery.
- Preserve paused SMS/calls/schedules. No test outreach or replay of historical leads.
- Local railway.toml was inspected earlier this session and starts uvicorn; start.sh invokes migrations. Verify deployed start settings, rather than applying old memory assumptions.

## Next actions in order

1. User credential handoff: disable the identified April Anthropic key, then verify disabled status. Computer-use policy requires user completion of authentication-credential changes. Replacing the key also requires user entry/submission; keep key values out of chat. Confirm dependent-service needs before resuming AI functionality.
2. Inspect the two Railway staged changes and exact deployed source. Map current Anthropic consumers, then coordinate replacement with no broader permissions. Verify replacement functionality and old-key rejection without contacting sellers.
3. Inspect Supabase API key configuration and all consumers, including Vercel, Railway, Edge Functions, webhooks, scripts, and website frontends. Current official guidance permits old/new API keys together while migrating consumers; deactivate legacy keys only after all dependencies have moved. New secret keys are not JWTs. Do not blindly replace Bearer headers or disable JWT checks without equivalent authorization validation. Reference: https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys .
4. Map DATABASE_URL to its database and dependent services; coordinate password rotation separately from Supabase API keys. Identify whether REALTY_API_KEY is real and its provider.
5. Sign into OpenAI and Gemini provider consoles for the saved shared keys, review usage, rotate/revoke affected credentials, and update verified consumers.
6. Review audit/provider/GitHub/registry logs and inventory remaining Railway environments/shared variables. Record anomalies without copying secrets or private lead data.
7. Verify each replacement, old-credential rejection, deployment health, authenticated database access and CRM intake handoff. Do not call the incident contained until all affected credentials are invalidated.

## Tool and handoff notes

- Railway connector failed after authentication with missing link_id; browser read-only access works.
- A stale numeric browser target was automatically rejected; a fresh full accessibility snapshot verified the public URL field and the safe inspection completed. No action remains blocked by that rejection.
- Claude API keys tab is open to the April key's action menu; Supabase production and Railway Variables tabs retained for continuation. Passwords and credential values must never be pasted into this chat or committed.
- Repository was pulled before this documentation update. Only this incident checkpoint is intended for commit/push; no deployment authorization is implied by the documentation push.
