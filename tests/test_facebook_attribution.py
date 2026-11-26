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


def _plan(patch=None, expected=None):
    return {"lead_id": "lead", "meta_lead_id": "meta", "requires_review": True,
            "expected": expected or {"ad_campaign_id": None, "ad_creative_id": None},
            "patch": patch if patch is not None else {"ad_campaign_id": "c", "ad_creative_id": "k"}}


def test_apply_calls_audited_rpc_once_with_exact_arguments():
    from tools.facebook_attribution import apply_reconciliation
    db = MagicMock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data={"applied": True})
    assert apply_reconciliation(db, _plan(), actor=" julio ", reason=" ad launch ") == {"applied": True}
    db.rpc.assert_called_once_with("reconcile_facebook_lead_attribution", {
        "p_lead_id": "lead", "p_leadgen_id": "meta", "p_campaign_id": "c",
        "p_creative_id": "k", "p_actor": "julio", "p_reason": "ad launch"})
    db.table.assert_not_called()


def test_apply_empty_patch_makes_no_database_call():
    from tools.facebook_attribution import apply_reconciliation
    db = MagicMock()
    out = apply_reconciliation(db, _plan(patch={}), actor="a", reason="r")
    assert out["applied"] is False
    db.rpc.assert_not_called()


@pytest.mark.parametrize("plan,actor,reason", [
    (None, "a", "r"), ({**_plan(), "requires_review": False}, "a", "r"),
    (_plan(), "", "r"), (_plan(), "a", " "),
    (_plan(patch={"owner_id": "x"}), "a", "r"),
])
def test_apply_rejects_unreviewed_or_unaudited_requests(plan, actor, reason):
    from tools.facebook_attribution import apply_reconciliation
    db = MagicMock()
    with pytest.raises(ValueError):
        apply_reconciliation(db, plan, actor=actor, reason=reason)
    db.rpc.assert_not_called()


def test_apply_propagates_database_failure():
    from tools.facebook_attribution import apply_reconciliation
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = RuntimeError("conflict")
    with pytest.raises(RuntimeError):
        apply_reconciliation(db, _plan(), actor="a", reason="r")
