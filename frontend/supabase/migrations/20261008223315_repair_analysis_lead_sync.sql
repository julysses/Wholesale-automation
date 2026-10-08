-- Offer recommendations remain on the analysis; offer_price is an actual offer,
-- not an estimate. Do not invent an offered price while saving analysis.
CREATE OR REPLACE FUNCTION public.sync_deal_to_lead()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 UPDATE public.leads SET estimated_arv=NEW.arv_low, mao=NEW.mao,
 estimated_repairs=coalesce(NEW.repair_cost_mid,NEW.repair_cost_high,estimated_repairs)
 WHERE id=NEW.lead_id;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.sync_deal_to_lead() FROM PUBLIC,anon,authenticated;
