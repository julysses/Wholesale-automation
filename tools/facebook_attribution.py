"""Resolve registered Facebook mappings without creating campaigns or sending outreach."""


def resolve_attribution(db, *, ad_id=None, campaign_id=None):
    """Return only unambiguous, consistent Facebook campaign/creative mappings.

    An ad mapping can supply campaign lineage when Meta omits campaign_id.
    Missing, duplicate or conflicting mappings remain unattributed for review.
    Database failures propagate to the caller; they are not proof of no mapping.
    """
    if ad_id:
        creatives = db.table("ad_creatives").select("id,campaign_id").eq(
            "external_ad_id", ad_id
        ).limit(2).execute().data
        if len(creatives) != 1 or not creatives[0].get("campaign_id"):
            return {}
        creative = creatives[0]
        query = db.table("ad_campaigns").select("id,external_campaign_id").eq(
            "id", creative["campaign_id"]
        ).eq("platform", "facebook")
        campaigns = query.limit(2).execute().data
        if len(campaigns) != 1:
            return {}
        campaign = campaigns[0]
        if campaign_id and campaign.get("external_campaign_id") != campaign_id:
            return {}
        return {"ad_campaign_id": campaign["id"], "ad_creative_id": creative["id"]}
    if campaign_id:
        campaigns = db.table("ad_campaigns").select("id").eq(
            "external_campaign_id", campaign_id
        ).eq("platform", "facebook").limit(2).execute().data
        if len(campaigns) == 1:
            return {"ad_campaign_id": campaigns[0]["id"]}
    return {}


def plan_reconciliation(*, lead, receipt, meta_lead_id, mapping):
    """Build a review-only patch; never write records or invoke intake/outreach.

    Caller must obtain authoritative Meta lineage before supplying mapping.
    Existing non-null attribution is never overwritten. Applying this plan
    requires a separately reviewed atomic compare-and-set and audit operation.
    """
    if not meta_lead_id or receipt.get("leadgen_id") != meta_lead_id:
        raise ValueError("Meta lead identity mismatch")
    if not lead.get("id") or receipt.get("lead_id") != lead["id"]:
        raise ValueError("Receipt does not belong to lead")
    if lead.get("source") != "facebook_lead_ad":
        raise ValueError("Not a Facebook inquiry")
    allowed = {"ad_campaign_id", "ad_creative_id"}
    if not mapping or set(mapping) - allowed or not mapping.get("ad_campaign_id"):
        raise ValueError("Complete campaign mapping required")
    patch = {}
    for key, value in mapping.items():
        if not value:
            raise ValueError("Empty attribution mapping")
        existing = lead.get(key)
        if existing is not None and existing != value:
            raise ValueError("Existing attribution conflicts")
        if existing is None:
            patch[key] = value
    return {"lead_id": lead["id"], "meta_lead_id": meta_lead_id,
            "expected": {key: lead.get(key) for key in allowed},
            "patch": patch, "requires_review": True}
