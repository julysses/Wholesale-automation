# County tax snapshot collectors

October 13, 2026. Implemented and locally exercised against full official archives. Output is a property-review queue; it does not assert current delinquency, a new CRM lead, tracing eligibility or SMS permission.

## Reproduce

Use Python 3.9+ and Node with the checked-in pipeline dependencies. Store archives/manifests outside Git in a private working directory:

```sh
python3 pipeline/collectors/fetch_tax_roll.py --county Collin --workspace /private/path/new-run
python3 pipeline/collectors/fetch_tax_roll.py --county Dallas --workspace /private/path/another-new-run
```

The fetcher discovers exactly one current ZIP link on the official source page, restricts redirects to its county host, bounds downloads and expansion, reads ZIP members without extracting paths, and records download URL/time/hash. Existing workspaces are not overwritten. A failed run writes a FAILED marker and never submits data.

For already downloaded ZIPs:

```sh
python3 pipeline/collectors/tax_roll.py --county Collin --archive /private/path/source.zip --output /private/path/new-manifests
```

Source files are UTF-8 fixed-width **characters**. The observed Collin account file has 950 characters, with five accented-name rows one byte longer. Transaction file uses the documented224-character layout independently. Both860/950-character account and224/226-character transaction layouts are supported. Unknown widths fail. No field offsets are inferred from addresses or example values.

## Source evidence

- Dallas: https://www.dallascounty.org/departments/tax/tax-roll.php . Current linked ZIP on inspection: https://www.dallascounty.org/Assets/uploads/docs/tax/trw/trwfile.755938.zip . Official2026layout: https://www.dallascounty.org/Assets/uploads/docs/tax/trw/File-Layout-New.pdf ; accompanying archive text confirms implied decimals. Weekly archive file date2026-10-12, SHA256`e294578e7480f60805b98976114e94bd4a091964210881ff2ffe174576f77b49`.
- Collin: https://www.collincountytx.gov/Tax-Assessor/property-taxes . Linked delinquency ZIP: https://www.collincountytx.gov/docs/default-source/tax-assessor/tax-rolls/delinquent-tax-roll.zip?sfvrsn=f82c86af_2 . Layout: https://www.collincountytx.gov/docs/default-source/tax-assessor/tax-rolls/file-layout.pdf?sfvrsn=3387249e_1 . Archive date2026-10-10, SHA256`dd8fdfade916e506552ab3ce71c67084fc1f3507907e12f127908b959a379f6b`.
- Both source pages describe weekly publication. Collector refuses future snapshots and snapshots older than10days. The date is a snapshot date, never a filing date. Dallas sample archive is2017and must not be treated as current data.

## Verified extraction

| County | Input | Review candidates | Batches |
|---|---|---:|---:|
| Dallas | 5,238,307 rows,534characters each | 30,516 accounts | 62 |
| Collin | 21,923 accounts;235,535 transactions | 9,182 real-property accounts | 19 |

Dallas: selects rollR, positive remaining levy, due date before snapshot. Excludes1,485,257non-real rows,3,161,978nonpositive rows,945not-past-due rows.2942duplicate account/year/jurisdiction rows create explicit review holds; affected account totals are withheld. Existing owner/parcel/mailing conflicts are flagged. Remaining levy excludes penalties/fees and is kept only in raw evidence, not represented as a current total due. Dallas does not supply verified situs in this layout: mailing address/city/ZIP are never copied into property fields.

Collin: filters real roll001, excludes12,741other accounts. Each account balance reconciles to its transactions; all annual counts/amounts and the ALL control reconcile exactly to51,374,307.09. This is the **whole published file** control, including excluded non-real accounts, not the real-property candidate subtotal. Deferrals, payment status and legal-proceeding fields produce review flags. Mailing geography is separate from the supplied situs street. Archive balances remain snapshot evidence, not verified current payoff amounts.

Both output null current amount_owed, snapshot_onlytrue, identity_verifiedfalse and partial/coverage_completefalse. All81batches passed schema, hash, source, size, manifest consistency and cross-batch unique-ID validation. No archive or personal rows are committed to Git. Candidate overlap across counties/source lists and existing CRM records still requires reconciliation.

## Scoped delivery client

`pipeline/collectors/deliver.mjs` validates the entire batch set before sending. Configure `INGEST_KEY_ID` and `INGEST_TOKEN` through a secret store, then:

```sh
node pipeline/collectors/deliver.mjs /private/path/manifests tbhwxgfzbiaqjurghntj
```

Only the exact Supabase ingestion HTTPS path is accepted. Redirects are rejected. An atomic private journal preserves pending batch and immutable payload-set hash; uncertain responses retry the same run/payload. Every acknowledgement must match run/batch/state/count. Replays recheck the endpoint rather than trust the local journal. Ingress acceptance never claims CRM lead creation. Verify stored SQL counts, jobs, review tasks and no duplicate side effects separately.

## Remaining acceptance

- Restricted connection and source-scoped secret provisioning in rehearsal.
- Synthetic delivery/replay/denial proof, followed by reviewed bounded real ingestion and task reconciliation.
- Validate duplicate/supplemental Dallas rows, current tax-account status and county/property identity; no trace spending from these candidate counts.
- Foreclosure notice extraction, full document review and supervised coverage remain separate.
