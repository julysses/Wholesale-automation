-- ── Migration 015: priority_rank recompute ────────────────────────────────────
--
-- The Precision Targeting Panel and Step 4 of the dashboard workflow read
-- leads.precision_tier / leads.priority_rank (added in 006_deal_analyzer.sql).
-- Claude auto-scoring writes precision_tier per-lead, but priority_rank is a
-- global ordering that has to be recomputed across the whole tiered set
-- whenever scores change — this function does that recompute on demand.

CREATE OR REPLACE FUNCTION recompute_priority_ranks()
RETURNS void AS $$
BEGIN
  UPDATE leads l SET priority_rank = ranked.rn
  FROM (
    SELECT id, ROW_NUMBER() OVER (ORDER BY total_score DESC) AS rn
    FROM leads
    WHERE precision_tier IS NOT NULL
  ) ranked
  WHERE l.id = ranked.id;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION recompute_priority_ranks() TO authenticated;
