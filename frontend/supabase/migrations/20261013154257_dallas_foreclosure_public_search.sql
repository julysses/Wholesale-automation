-- County clerk directs notices filed from February 24, 2026 to Public Search.
-- Evidence checked October 13, 2026:
-- https://www.dallascounty.org/government/county-clerk/recording/foreclosures.php
-- Change only the known seeded endpoint; preserve operator customizations,
-- source enabled state, schedule, credentials and all historical receipts.
UPDATE wholesale_ingest.sources
SET source_url = 'https://dallas.tx.publicsearch.us/',
    allowed_hosts = ARRAY(SELECT DISTINCT host FROM unnest(allowed_hosts || ARRAY['dallas.tx.publicsearch.us']) AS host ORDER BY host)
WHERE source_key = 'tx-dallas-pre_foreclosure'
  AND source_url = 'https://www.dallascounty.org/government/county-clerk/recording/foreclosures.php';
