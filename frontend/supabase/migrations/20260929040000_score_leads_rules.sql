-- Set-based lead screen: scores every eligible lead in ONE statement inside Postgres.
-- Mirrors tools/lead_scoring_engine.py (the Python engine stays as fallback and
-- as the tested reference; tests/test_lead_scoring_engine.py pins the shared rules).
--
-- CTEs are MATERIALIZED on purpose: without it Postgres inlines them and re-evaluates the regex/
-- street-key expressions once per reference (a full run then exceeds 120s instead of ~30s).
-- Why in the database: the API-driven loop paid ~10 HTTP round trips per 1,000 leads
-- (about 1 minute); this scores the whole backlog in a few seconds.

CREATE OR REPLACE FUNCTION public.lead_street_key(raw text)
RETURNS text LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  s text := lower(coalesce(raw, ''));
BEGIN
  s := regexp_replace(s, '[^a-z0-9 ]+', ' ', 'g');
  s := regexp_replace(s, '\ystreet\y', 'st', 'g');
  s := regexp_replace(s, '\yavenue\y', 'ave', 'g');
  s := regexp_replace(s, '\ydrive\y', 'dr', 'g');
  s := regexp_replace(s, '\ylane\y', 'ln', 'g');
  s := regexp_replace(s, '\yroad\y', 'rd', 'g');
  s := regexp_replace(s, '\ycourt\y', 'ct', 'g');
  s := regexp_replace(s, '\yboulevard\y', 'blvd', 'g');
  s := regexp_replace(s, '\yplace\y', 'pl', 'g');
  s := regexp_replace(s, '\ycircle\y', 'cir', 'g');
  s := regexp_replace(s, '\ytrail\y', 'trl', 'g');
  s := regexp_replace(s, '\yparkway\y', 'pkwy', 'g');
  s := regexp_replace(s, '\yhighway\y', 'hwy', 'g');
  s := regexp_replace(s, '\y(north|south|east|west)\y', '', 'g');
  RETURN btrim(regexp_replace(s, '\s+', ' ', 'g'));
END;
$$;

CREATE OR REPLACE FUNCTION public.score_leads_rules(
  p_ids uuid[] DEFAULT NULL,
  p_list_id uuid DEFAULT NULL,
  p_rescore boolean DEFAULT false,
  p_include_errors boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql
SET statement_timeout = '120s'
AS $fn$
DECLARE
  v_scored int := 0;
BEGIN
  WITH src AS MATERIALIZED (
    SELECT
      l.id, l.status, l.contact_attempts, l.dnc,
      coalesce(l.property_type, '') AS ptype,
      l.estimated_arv AS arv, l.loan_balance AS loan, l.estimated_equity_pct AS eq_pct,
      l.asking_price AS ask, l.sqft, l.bedrooms AS beds, l.year_built AS yr,
      lower(regexp_replace(concat_ws(' ', l.motivation_tag, l.source, l.seller_notes, l.internal_notes), '[_+/]+', ' ', 'g')) AS blob,
      l.internal_notes, l.source,
      (SELECT count(*) FROM unnest(ARRAY[l.owner_phone_1, l.owner_phone_2, l.owner_phone_3]) p
        WHERE nullif(btrim(p), '') IS NOT NULL AND p NOT IN ('None', 'nan'))::int AS phones,
      (nullif(btrim(l.owner_email), '') IS NULL OR l.owner_email IN ('None', 'nan')) AS no_email,
      public.lead_street_key(l.owner_mailing_address) AS mail_key,
      public.lead_street_key(l.property_address) AS prop_key
    FROM public.leads l
    WHERE (p_ids IS NULL OR l.id = ANY (p_ids))
      AND (p_list_id IS NULL OR l.list_id = p_list_id)
      AND (p_rescore OR l.score_motivation IS NULL)
      AND (p_include_errors OR l.status IS DISTINCT FROM 'scoring_error')
  ),
  sig AS MATERIALIZED (
    SELECT s.*,
      (blob ~ 'probate|inherit|estate of|deceased|\yheir\y') AS probate,
      (blob ~ 'pre[[:space:]-]?foreclos|\yprefor\y|foreclos|\ylis pendens\y|\ynod\y|notice of default|auction|trustee sale') AS prefor,
      (blob ~ 'delinq|tax[[:space:]-]?(lien|sale|roll)|back tax') AS tax,
      (blob ~ 'code (violation|enforcement)|condemn|unsafe|nuisance') AS code,
      (blob ~ 'vacant|abandon|empty') AS vacant,
      (blob ~ 'absentee|non[[:space:]-]?owner|out[[:space:]-]?of[[:space:]-]?(state|town)') AS absentee_txt,
      (blob ~ 'divorce|bankrupt|chapter 7|chapter 13') AS life,
      (blob ~ 'tired landlord|landlord|evict|tenant') AS tired,
      (blob ~ 'water shut|utility (shut|disconnect)|shutoff') AS util,
      (blob ~ 'fire damage|fire[[:space:]-]?damaged|\yflood|\yhail\y|\ystorm|foundation|\ymold\y|\yroof') AS damaged,
      (blob ~ 'high equity|free and clear|no mortgage|paid off|\ylow ltv\y') AS high_eq,
      (blob ~ 'need(s)? to sell|must sell|asap|relocat|behind on|hardship|job loss|as[[:space:]-]?is') AS urgent,
      CASE
        WHEN mail_key = '' OR prop_key = '' THEN NULL
        WHEN mail_key ~ '^(po|p o) box\y' OR mail_key ~ '\y(ste|suite)\y' THEN true
        ELSE mail_key <> prop_key
      END AS mail_abs,
      coalesce((regexp_match(internal_notes, 'stack_count=([0-9]+)'))[1]::int,
        CASE WHEN source LIKE '%|%'
          THEN (SELECT count(*) FROM unnest(string_to_array(source, '|')) x WHERE btrim(x) <> '')::int
          ELSE 1 END) AS stack,
      (ptype ~* 'business personal|personal property|mineral|utility|inventory') AS not_re,
      ((ptype ~* 'mobile|manufactured|trailer|land|lot\y|acre|multi|duplex|triplex|fourplex|quad|apartment|commercial|condo|coop|co-op|industrial|farm|^other$') OR prop_key !~ '^[0-9]') AS non_sfr,
      (ptype ~* 'single[[:space:]-]?family|\ysfr\y|residential|\yhouse\y|\yhome\y|townhome') AS resid
    FROM src s
  ),
  sig2 AS MATERIALIZED (
    SELECT g.*, (absentee_txt OR coalesce(mail_abs, false)) AS absentee FROM sig g
  ),
  mot AS MATERIALIZED (
    SELECT g.*,
      ( 3*probate::int + 3*prefor::int + 2*tax::int + 2*code::int + 2*util::int + 2*vacant::int
        + 2*life::int + 1.5*tired::int + absentee::int + damaged::int + 1.5*urgent::int
        + 0.5*high_eq::int + CASE WHEN stack >= 3 THEN 2 WHEN stack = 2 THEN 1 ELSE 0 END ) AS pts,
      (probate OR prefor OR tax OR code OR util OR vacant OR life OR tired OR absentee OR damaged OR urgent) AS distress,
      greatest(3*prefor::int, 2*probate::int, 2*tax::int, 2*code::int, 2*util::int, 2*life::int, 2*urgent::int) AS clock,
      coalesce(eq_pct, CASE WHEN arv > 0 AND loan IS NOT NULL THEN greatest(0, (arv - loan) / arv * 100) END) AS eq_calc,
      CASE WHEN coalesce(arv, 0) > 0 THEN arv ELSE ask END AS val,
      -- buy-box tally
      ( (non_sfr OR resid)::int
        + (coalesce(sqft, 0) > 0)::int + (coalesce(beds, 0) > 0)::int
        + (coalesce(yr, 0) > 0)::int
        + (coalesce(CASE WHEN coalesce(arv, 0) > 0 THEN arv ELSE ask END, 0) > 0)::int ) AS checks,
      ( CASE WHEN non_sfr THEN -2 WHEN resid THEN 1 ELSE 0 END
        + CASE WHEN coalesce(sqft, 0) > 0 THEN CASE WHEN sqft BETWEEN 900 AND 3200 THEN 1 ELSE -1 END ELSE 0 END
        + CASE WHEN coalesce(beds, 0) > 0 THEN CASE WHEN beds >= 3 THEN 1 ELSE -1 END ELSE 0 END
        + CASE WHEN coalesce(yr, 0) > 0 THEN CASE WHEN yr >= 1960 THEN 1 ELSE -1 END ELSE 0 END
        + CASE WHEN coalesce(CASE WHEN coalesce(arv, 0) > 0 THEN arv ELSE ask END, 0) > 0
               THEN CASE WHEN CASE WHEN coalesce(arv, 0) > 0 THEN arv ELSE ask END BETWEEN 90000 AND 450000 THEN 1 ELSE -1 END
               ELSE 0 END ) AS buybox
    FROM sig2 g
  ),
  fit AS MATERIALIZED (
    SELECT m.*,
      CASE
        WHEN checks = 0 THEN 'unknown'
        WHEN non_sfr THEN 'weak'
        WHEN buybox::numeric / checks >= 0.6 AND checks >= 2 THEN 'strong'
        WHEN buybox::numeric / checks >= 0 THEN 'ok'
        ELSE 'weak'
      END AS fit_label
    FROM mot m
  ),
  fac AS MATERIALIZED (
    SELECT f.*,
      CASE WHEN pts >= 3 THEN 3 WHEN pts >= 1.5 THEN 2 ELSE 1 END AS f_mot,
      greatest(1, least(3,
        (CASE WHEN clock >= 3 OR (clock >= 2 AND stack >= 2) THEN 3
              WHEN clock >= 2 OR vacant OR stack >= 2 THEN 2 ELSE 1 END)
        - CASE WHEN coalesce(contact_attempts, 0) >= 4
                AND (CASE WHEN clock >= 3 OR (clock >= 2 AND stack >= 2) THEN 3
                          WHEN clock >= 2 OR vacant OR stack >= 2 THEN 2 ELSE 1 END) > 1 THEN 1 ELSE 0 END
      )) AS f_time,
      CASE
        WHEN eq_calc IS NOT NULL THEN CASE WHEN eq_calc >= 50 THEN 3 WHEN eq_calc >= 30 THEN 2 ELSE 1 END
        WHEN high_eq THEN 3
        WHEN tired OR absentee THEN 2
        WHEN distress THEN 2
        ELSE 1
      END AS f_eq,
      least(3, CASE fit_label
        WHEN 'unknown' THEN 2 WHEN 'strong' THEN 3 WHEN 'ok' THEN 2 ELSE 1 END
        + CASE WHEN damaged AND fit_label IN ('strong', 'ok') THEN 1 ELSE 0 END) AS f_cond,
      (phones = 0 AND no_email) AS needs_skip
    FROM fit f
  ),
  fin AS MATERIALIZED (
    SELECT c.*,
      CASE WHEN dnc THEN 1 ELSE
        greatest(1, least(3,
          CASE
            WHEN coalesce(ask, 0) > 0 AND coalesce(arv, 0) > 0
              THEN CASE WHEN ask / arv <= 0.70 THEN 3 WHEN ask / arv <= 0.85 THEN 2 ELSE 1 END
            WHEN coalesce(ask, 0) > 0 THEN 2
            ELSE 2 END
          + CASE WHEN NOT (phones = 0 AND no_email) AND phones >= 2
                      AND (CASE WHEN coalesce(ask, 0) > 0 AND coalesce(arv, 0) > 0
                                THEN CASE WHEN ask / arv <= 0.70 THEN 3 WHEN ask / arv <= 0.85 THEN 2 ELSE 1 END
                                WHEN coalesce(ask, 0) > 0 THEN 2 ELSE 2 END) < 3 THEN 1 ELSE 0 END
        ))
      END AS f_flex
    FROM fac c
  ),
  scored AS MATERIALIZED (
    SELECT n.*,
      CASE WHEN not_re THEN 5 ELSE f_mot + f_time + f_eq + f_cond + f_flex END AS total,
      CASE WHEN not_re THEN 1 ELSE f_mot END AS s_mot,
      CASE WHEN not_re THEN 1 ELSE f_time END AS s_time,
      CASE WHEN not_re THEN 1 ELSE f_eq END AS s_eq,
      CASE WHEN not_re THEN 1 ELSE f_cond END AS s_cond,
      CASE WHEN not_re THEN 1 ELSE f_flex END AS s_flex
    FROM fin n
  ),
  tiered AS MATERIALIZED (
    SELECT t.*,
      CASE WHEN s_mot < 2 THEN 'COLD' WHEN total >= 13 AND NOT (coalesce(dnc, false)) THEN 'HOT'
           WHEN total >= 13 THEN 'WARM'
           WHEN total >= 8 THEN 'WARM' ELSE 'COLD' END AS tier
    FROM scored t
  ),
  final AS MATERIALIZED (
    SELECT t.id, t.status AS old_status,
      t.s_mot, t.s_time, t.s_eq, t.s_cond, t.s_flex, t.tier, t.total,
      tier || ' (' || total || '/15): ' ||
        CASE WHEN not_re THEN 'Not real property (' || ptype || ') - cannot be assigned'
        ELSE array_to_string(array_remove(ARRAY[
          CASE WHEN distress THEN 'Distress: ' || concat_ws(', ',
            CASE WHEN probate THEN 'probate' END, CASE WHEN prefor THEN 'pre foreclosure' END,
            CASE WHEN tax THEN 'tax delinquent' END, CASE WHEN code THEN 'code violation' END,
            CASE WHEN util THEN 'utility shutoff' END, CASE WHEN vacant THEN 'vacant' END,
            CASE WHEN life THEN 'life event' END, CASE WHEN tired THEN 'tired landlord' END,
            CASE WHEN absentee THEN 'absentee' END, CASE WHEN damaged THEN 'damaged' END,
            CASE WHEN urgent THEN 'urgent language' END) END,
          CASE WHEN stack >= 2 THEN 'Stacked on ' || stack || ' lists' END,
          CASE WHEN mail_abs IS FALSE THEN 'Owner-occupied' END,
          CASE WHEN clock >= 3 OR (clock >= 2 AND stack >= 2) THEN 'Hard deadline pressure' END,
          CASE WHEN eq_calc IS NOT NULL THEN '~' || round(eq_calc) || '% equity' END,
          CASE fit_label WHEN 'strong' THEN 'Fits institutional/flip buy-box'
                         WHEN 'weak' THEN 'Narrow exit (small buyer pool)' END,
          CASE WHEN needs_skip THEN 'No phone/email - skip trace first' END
        ], NULL), '; ') END
        || '.' ||
        CASE
          WHEN not_re THEN ' Next: Suppress: not a wholesale target'
          WHEN dnc THEN ' Next: Do not call; direct mail only if legal'
          WHEN tier = 'HOT' THEN ' Next: ' || CASE WHEN needs_skip THEN 'Skip trace first, then call' ELSE 'Call' END
                                  || ' today; ' || CASE WHEN fit_label = 'weak' THEN 'confirm a buyer exists before contracting' ELSE 'pull comps and line up an end buyer' END
          WHEN tier = 'WARM' THEN ' Next: ' || CASE WHEN needs_skip THEN 'Skip trace first, then sms' ELSE 'SMS' END || ' + follow-up call this week'
          ELSE ' Next: Nurture only; revisit if a new distress signal appears'
        END AS summary
    FROM tiered t
  ),
  upd AS (
    UPDATE public.leads l SET
      score_motivation = f.s_mot, score_timeline = f.s_time, score_equity = f.s_eq,
      score_condition = f.s_cond, score_flexibility = f.s_flex,
      ai_qualification_summary = left(f.summary, 500),
      -- never rewrite the pipeline stage of a lead a human has already worked
      status = CASE WHEN f.old_status IN ('new', 'qualified_hot', 'qualified_warm', 'qualified_cold', 'scoring_error')
                    OR f.old_status IS NULL
                    THEN 'qualified_' || lower(f.tier) ELSE f.old_status END,
      precision_tier = CASE f.tier WHEN 'HOT' THEN 1 WHEN 'WARM' THEN 2 ELSE 3 END
    FROM final f
    WHERE l.id = f.id
      AND (l.score_motivation, l.score_timeline, l.score_equity, l.score_condition, l.score_flexibility,
           l.ai_qualification_summary)
          IS DISTINCT FROM (f.s_mot, f.s_time, f.s_eq, f.s_cond, f.s_flex, left(f.summary, 500))
    RETURNING l.id
  )
  SELECT count(*) INTO v_scored FROM upd;

  PERFORM public.recompute_priority_ranks();

  RETURN jsonb_build_object(
    'scored', v_scored,
    'hot',  (SELECT count(*) FROM public.leads WHERE status = 'qualified_hot'),
    'warm', (SELECT count(*) FROM public.leads WHERE status = 'qualified_warm'),
    'cold', (SELECT count(*) FROM public.leads WHERE status = 'qualified_cold'),
    'unscored', (SELECT count(*) FROM public.leads WHERE score_motivation IS NULL AND status IS DISTINCT FROM 'scoring_error')
  );
END;
$fn$;

REVOKE ALL ON FUNCTION public.score_leads_rules(uuid[], uuid, boolean, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.score_leads_rules(uuid[], uuid, boolean, boolean) TO service_role;

-- Break ties within a score by the signals that matter, instead of arbitrarily.
CREATE OR REPLACE FUNCTION public.recompute_priority_ranks()
RETURNS void AS $$
BEGIN
  UPDATE leads l SET priority_rank = ranked.rn
  FROM (
    SELECT id, ROW_NUMBER() OVER (
      ORDER BY total_score DESC, score_motivation DESC, score_timeline DESC,
               score_equity DESC, created_at ASC, id
    ) AS rn
    FROM leads
    WHERE precision_tier IS NOT NULL
  ) ranked
  WHERE l.id = ranked.id AND l.priority_rank IS DISTINCT FROM ranked.rn;
END;
$$ LANGUAGE plpgsql;
