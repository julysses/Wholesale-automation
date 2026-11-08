# Website notification investigation — 2026-11-08

## Status

Investigation complete. Likely automated form spam; sender and intent are unconfirmed. No live configuration, records, queues, or application code changed. No test inquiries or outbound messages sent by this investigation.

## Verified evidence

- Read-only queries against Supabase project `dvzhzlipbwzzcliujzyz` matched the screenshot to submission `199efc27-3570-4e4d-bfd2-048fce0e43d1`, lead `b9b76ed4-511f-453f-8102-1be681813983`, at 2026-11-08 13:20:59 America/Chicago.
- Latest burst: four submissions between 13:20:50 and 13:21:30, covering contact, buyer, financing, and sell. Same email, different random-looking names/phones and meaningless free-text answers. Exact contact details deliberately omitted from this Git document.
- Another four-submission burst occurred Nov 8 at 04:59, and another Nov 7 at 05:52. All 12 were processed into leads; their operator notification records show owner email `accepted`. This is provider acceptance; the screenshot independently establishes receipt of one email.
- Each burst included a seller opt-in and scheduled an app-Twilio SMS job. At inspection all three jobs were `scheduled` with `claimed_at = null`; these records do not show a send. Submission IDs: `1da20791-b1ce-48d3-85ab-836aebafce2e`, `20e92a3b-a071-4914-b8c1-85983f507b93`, `8b570c58-ecfa-48e6-8582-9428df8aae57`.
- Four additional Jays submissions occurred Nov 1; one Nov 6 contact submission was a website-service solicitation. Do not classify every record as the same bot without review.

## Code trace and limits

- Fresh WholesaleOS clone, pulled successfully: `ad70c7c29d618efe3aad848a386ca1779f0e7b8f` on remote default branch `claude/ai-wholesaling-agency-KkDF1`. Do not assume this is the live deployment: live notification metadata includes scheduled SMS behavior absent from this default-branch implementation.
- Fresh website clone: `julysses/TheJaysDallas`, main `4ff642f20b92a6afef904de18ad7a576ae4dc7c7`.
- Website `src/app/api/intake/route.ts` validates intent, request UUID, fields, required values, and consent text, then forwards to `/api/forms/the-jays-dallas/submit`. No CAPTCHA, honeypot, or rate limit appears in that route. Platform-level controls were not audited.
- The forwarder sends only Content-Type, not original browser user agent/IP. Thus CRM `user_agent=node` and recorded IPs may describe the proxy, not the original visitor. Do not block these IPs or the node user agent as a spam fix.
- WholesaleOS `web/api/lead_forms_api.py` accepts syntactically valid answers, creates CRM records, and sends owner email independently of seller SMS consent. Screenshot wording matches this notification flow.
- Searched checked-out tests/scripts for screenshot strings; no match. This does not prove no external testing service is responsible. Website repo has no `.github` workflows. Sender attribution remains unknown.

## Remediation plan / resume

1. Establish exact currently deployed website and WholesaleOS commits before implementation or release; the CRM default branch is not sufficient evidence.
2. Add server-verified bot protection on website intake and protect the direct CRM submission route from bypass. Preserve legitimate inquiry retries and accessibility; do not classify names as spam solely by spelling.
3. Add durable submission throttling and trustworthy client provenance; preserve proxy boundaries and avoid IP-only blocking of shared infrastructure.
4. Quarantine suspicious inquiries before lead notifications and SMS scheduling, with review and release controls. Review the three identified unclaimed jobs before any future scheduler activation.
5. Use mocked/local tests to prove blocked submissions cannot create leads, alerts, or SMS jobs, while genuine submissions and retries work. Do not send fresh production tests without a controlled recipient plan.
6. Review and authorize live rollout and any historical-record/queue cleanup separately; preserve audit history rather than delete records.

## Handoff

Workspace: `/Users/juliodominguez/Documents/Codex/2026-11-08/look-at-the-wholesale-os-i`.
CRM checkout: `app`; website checkout: `jays`.
Investigation branch: `codex/website-spam-investigation-20261108`.
Only this documentation file changed. No application tests needed for this documentation-only update; verify with `git diff --check` and push the branch.
