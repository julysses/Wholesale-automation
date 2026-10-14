# County notice text extraction

The local worker extracts saved county images in bulk without a paid model service or document upload. It runs inside the normal filesystem sandbox using pinned Tesseract.js 7.0.0 and English language package 1.0.0. The earlier native Vision prototype remains unvalidated; its declined outside-sandbox execution is not used.

Install with `npm ci --prefix pipeline --ignore-scripts`. Language and WebAssembly files are local dependencies; runtime recognition accepts image bytes, never remote image URLs. Installation downloads packages, but recognition sends no notice content to a provider. Reference: [Tesseract local installation](https://github.com/naptha/tesseract.js/blob/master/docs/local-installation.md) and [recognition API](https://github.com/naptha/tesseract.js/blob/master/docs/api.md).

Build the capture manifest first with `capture_receipt_manifest.py`, using `--county Dallas` for Dallas PNGs or the default Collin JPEGs. Then run:

```sh
node pipeline/collectors/notice_ocr.mjs /private/county-root /private/captures.json /private/ocr-output 2
```

Concurrency is bounded to1–4. The worker validates every manifest identity, official URL, complete ordered page set, summary hash, image signature and image hash before starting. Each saved page contains its source identity, image hash, text/hash, confidence, text blocks and extraction timestamp. Output files use owner-only permissions and atomic replacement. Resume checks prevent retracing OCR work with different images, engine identity or altered text. Interrupted batches can restart against the same paths. Keep raw scans, text and owner data outside Git.

Empty or below85-confidence text is marked for additional review. This is an extraction-quality flag, not a calibrated probability and not a property-status decision. Every output has `verified:false` and `trace_eligible:false`, including high-confidence pages. OCR can confuse numbers, dates, legal descriptions, names and filing stamps; it does not establish title, present ownership, cancellation/postponement status or permission to contact.

This worker is an accepted local extraction component after a live smoke test; it is not an active daily schedule, production worker or completed structured-property verification pipeline. County matching, authoritative current-sale review, durable in-app verification and actual PropStream result acceptance remain separate gates. No paid tracing or outreach can be triggered by this script.
