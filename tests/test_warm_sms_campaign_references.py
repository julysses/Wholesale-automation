"""Interrupted WARM campaigns reconcile durable receipts instead of resending."""
from uuid import uuid4, uuid5
import pytest
from tests.test_backend_launch_contracts import Database, warm_row, sms
from web.api import marketing_api


@pytest.fixture
def campaign(monkeypatch, sms):
    row = warm_row()
    db = Database({"leads": [row]})
    monkeypatch.setattr(marketing_api, "get_supabase_client", lambda: db)
    body = marketing_api.BulkSMSRequest(request_id=uuid4(), lead_ids=[row["id"]])
    return db, row, body, sms


def receipt(row, body, status):
    return {"id": str(uuid5(body.request_id, f"warm-sms:{row['id']}")),
            "lead_id": row["id"], "phone_number": row["owner_phone_1"],
            "provider": "twilio", "direction": "outbound", "status": status,
            "body": body.template.format(first_name=row["owner_first_name"], address=row["property_address"])}


@pytest.mark.parametrize("status", ["accepted", "delivered", "failed", "unknown", "submitting"])
def test_retry_reconciles_receipt_without_send_or_duplicate_activity(campaign, status):
    db, row, body, sender = campaign
    db.tables["sms_events"] = [receipt(row, body, status)]
    result = marketing_api._process_bulk_sms(body)
    assert not sender.sends
    assert not db.tables.get("outreach_activity")
    key = "sent_count" if status in {"accepted", "delivered"} else "failed_count" if status == "failed" else "unknown_count"
    assert result[key] == 1


def test_changed_template_cannot_reuse_campaign_reference(campaign):
    db, row, body, sender = campaign
    db.tables["sms_events"] = [receipt(row, body, "delivered")]
    body.template = "Different request for {address}. Reply STOP to opt out."
    assert marketing_api._process_bulk_sms(body)["failed_count"] == 1
    assert not sender.sends


def test_new_reference_cannot_bypass_unknown_phone_on_another_lead(campaign):
    db, row, body, sender = campaign
    old = receipt(row, body, "unknown")
    old.update(id=str(uuid4()), lead_id=str(uuid4()))
    db.tables["sms_events"] = [old]
    assert marketing_api._process_bulk_sms(body)["unknown_count"] == 1
    assert not sender.sends


def test_new_send_uses_stable_message_id_and_retry_does_not_repeat(campaign, monkeypatch):
    db, row, body, sender = campaign
    def record_send(self, message, phone):
        self.sends.append((message, phone))
        db.tables.setdefault("sms_events", []).append(receipt(row, body, "accepted"))
        assert str(message.id) == receipt(row, body, "accepted")["id"]
        return True
    monkeypatch.setattr(sender, "send", record_send)
    assert marketing_api._process_bulk_sms(body)["sent_count"] == 1
    assert marketing_api._process_bulk_sms(body)["already_recorded_count"] == 1
    assert len(sender.sends) == 1
    assert len(db.tables["outreach_activity"]) == 1


def test_uncertain_dispatch_is_unknown_not_failed(campaign, monkeypatch):
    db, row, body, sender = campaign
    def record_unknown(self, message, phone):
        db.tables.setdefault("sms_events", []).append(receipt(row, body, "unknown"))
        return False
    monkeypatch.setattr(sender, "send", record_unknown)
    result = marketing_api._process_bulk_sms(body)
    assert result["unknown_count"] == 1
    assert result["failed_count"] == 0
    assert result["status"] == "partial"


def test_campaign_reference_required_before_any_dispatch():
    with pytest.raises(ValueError):
        marketing_api.BulkSMSRequest(lead_ids=[uuid4()])
