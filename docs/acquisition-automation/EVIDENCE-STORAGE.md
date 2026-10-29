# Acquisition evidence — private storage and verification

## Current implementation boundary

`schemas/acquisition_evidence.py` defines an internal immutable artifact descriptor. `tools/acquisition_evidence.py` verifies streamed object bytes through the existing user-authenticated `AcquisitionStore` client. No public endpoint accepts this descriptor. No bucket, object, registry table, upload route or production policy was created by this increment, and no real document was downloaded.

Read-only catalog inspection on 2026-10-29 UTC found storage.objects/storage.buckets, no existing public table matching document/evidence names, zero storage buckets and zero storage policies. This narrow inventory is not a complete schema inventory or permission test; inspect columns, constraints, grants, policies and migration history before the additive registry/storage migration.

The authenticated object path follows [Supabase's documented private download route](https://supabase.com/docs/guides/storage/serving/downloads). Private downloads require the user's authorization and applicable [Storage access controls](https://supabase.com/docs/guides/storage/buckets/fundamentals). Do not expose a public bucket or substitute service-role credentials.

## Implemented byte-verification contract

- Expected workspace, campaign and purpose must match the descriptor. Revoked, expired or not-yet-created evidence is rejected before I/O. Supported initial types are PDF, PNG, JPEG and plain text; the descriptor is strict, immutable and limited to 10 MiB.
- The fixed future bucket is `acquisition-evidence`. The object key is derived from workspace UUID / artifact UUID / SHA-256, with no user filename, URL, traversal, query or mutable latest alias. This is a naming contract, not a claim that the bucket exists.
- Use the existing configured HTTPS project origin and user bearer/public key. Reject unexpected URL paths, credentials in the URL, queries/fragments and missing user authorization. No signing, service-role fallback, redirects or public URL generation.
- Stream exact raw bytes with a size ceiling, per-read timeout and a 15-second total deadline. Reject non-200/partial results, compression, incompatible media type, invalid length, truncated/oversized content and hash mismatch. Recheck retention and clock order after reading. Responses and failures do not expose document bytes, upstream error bodies, credentials or URLs.
- Success is `bytes_verified` with source identity, exact digest/size/type and check/retention timestamps. Both content approval and execution authority remain false. A byte match is not malware scanning, factual verification, legal approval, immutable-storage proof or authorization to mail.

## Required next integration

1. Inventory full live/local catalog and migration history. Add the artifact registry using workspace/campaign foreign keys, immutable provenance/digest/type/size, revocation state, retention policy/version and audit records. Reuse an equivalent existing table if the expanded inventory identifies one.
2. Add a private bucket and tightly scoped object policies in a local forward-only migration. Enforce actual current workspace membership/session/role and exact registry key. Deny replacement/upsert, cross-workspace paths, raw unauthorized mutation and unaudited deletion. SQL must not directly insert/delete Storage object metadata in place of Storage APIs.
3. Implement bounded authenticated upload/quarantine, allowed-type validation and scanning. Bind accepted registry metadata to server-computed bytes; client hashes are expectations, not verification. Verify bucket privacy before accepting evidence. Do not cache user authorization or use signed links as durable evidence.
4. Load descriptors server-side from the protected registry. After byte verification, lock/recheck registry version, revocation, retention, role/session and referenced review sources in the approval transaction. Persist immutable verification provenance bound to the exact artifact and review. A standalone transport receipt must not bypass those checks, and the current mail reference/hash fields remain attestations until this integration exists.
5. Add controlled retention and legal-hold handling, audited purge reconciliation and missing-object invalidation. Determine policy durations through the approval workflow; the transport's descriptor timestamp is not an approved retention policy.
6. Replace manual reference/digest entry with a guided evidence upload/selection step in the existing app flow, while retaining unknown-request recovery. Test real Storage/JWT/RLS across roles/workspaces, overwrite/revocation races, missing/tampered objects, expiry and recovery before any production migration or live approval acceptance.

## Isolated validation

Synthetic streaming tests cover exact bytes and forwarded user authority, scope/purpose and timestamp failures before I/O, invalid descriptors, unsafe origins, absent auth with a configured service key, redirects and errors without response-body reads, oversized headers, wrong media/compression, truncation/tampering, early oversize termination, post-read expiry, timeout/resource closure and the existing store integration seam. The API regression suite remains unchanged. These tests use an HTTP mock transport with external networking disabled; they do not prove deployed Storage policies or provider acceptance.
