from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools.facebook_attribution import resolve_attribution


def database(*results):
    db = MagicMock()
    query = db.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = [SimpleNamespace(data=x) for x in results]
    return db


def test_ad_supplies_missing_campaign():
    db = database([{"id": "creative", "campaign_id": "campaign"}],
                  [{"id": "campaign", "external_campaign_id": "meta-campaign"}])
    assert resolve_attribution(db, ad_id="meta-ad") == {
        "ad_campaign_id": "campaign", "ad_creative_id": "creative"}
    db.table.return_value.eq.assert_any_call("platform", "facebook")


@pytest.mark.parametrize("rows", [[], [{"id": "a"}, {"id": "b"}]])
def test_ambiguous_or_missing_ad_is_not_guessed(rows):
    assert resolve_attribution(database(rows), ad_id="ad", campaign_id="campaign") == {}


def test_conflicting_lineage_is_rejected():
    db = database([{"id": "creative", "campaign_id": "campaign"}],
                  [{"id": "campaign", "external_campaign_id": "other"}])
    assert resolve_attribution(db, ad_id="ad", campaign_id="claimed") == {}


def test_campaign_only_and_no_identifiers():
    assert resolve_attribution(database([{"id": "campaign"}]), campaign_id="meta") == {
        "ad_campaign_id": "campaign"}
    db = database()
    assert resolve_attribution(db) == {}
    db.table.assert_not_called()


def test_reconciliation_is_idempotent_and_does_not_mutate_input():
    from tools.facebook_attribution import plan_reconciliation
    lead = {"id": "lead", "source": "facebook_lead_ad"}
    receipt = {"leadgen_id": "meta", "lead_id": "lead"}
    mapping = {"ad_campaign_id": "campaign", "ad_creative_id": "creative"}
    plan = plan_reconciliation(lead=lead, receipt=receipt, meta_lead_id="meta", mapping=mapping)
    assert plan["patch"] == mapping
    assert plan["requires_review"] is True
    assert "ad_campaign_id" not in lead
    assert plan_reconciliation(lead={**lead, **mapping}, receipt=receipt,
                               meta_lead_id="meta", mapping=mapping)["patch"] == {}


@pytest.mark.parametrize("lead,receipt", [
    ({"id": "lead", "source": "facebook_lead_ad"}, {"leadgen_id": "wrong", "lead_id": "lead"}),
    ({"id": "lead", "source": "facebook_lead_ad"}, {"leadgen_id": "meta", "lead_id": "other"}),
    ({"id": "lead", "source": "website"}, {"leadgen_id": "meta", "lead_id": "lead"}),
    ({"id": "lead", "source": "facebook_lead_ad", "ad_campaign_id": "other"},
     {"leadgen_id": "meta", "lead_id": "lead"}),
])
def test_reconciliation_rejects_identity_or_attribution_conflict(lead, receipt):
    from tools.facebook_attribution import plan_reconciliation
    with pytest.raises(ValueError):
        plan_reconciliation(lead=lead, receipt=receipt, meta_lead_id="meta",
                            mapping={"ad_campaign_id": "campaign"})
