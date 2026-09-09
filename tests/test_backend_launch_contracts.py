"""Launch regressions for saved imports, form qualification, and mocked SMS delivery."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from web import api
from web.api import buyers_api, lead_forms_api, marketing_api


class Table:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters = []
        self.action = "select"
        self.payload = None
        self.span = None
        self.max_rows = None
        self.sort_key = None
        self.single_row = False

    def select(self, *_args, **_kwargs): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self
    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self
    def order(self, key, desc=False):
        self.sort_key = (key, desc)
        return self
    def range(self, start, end):
        self.span = (start, end)
        self.db.pages.append((start, end))
        return self
    def limit(self, limit):
        self.max_rows = limit
        return self
    def single(self):
        self.single_row = True
        return self
    def insert(self, payload, **_kwargs):
        self.action, self.payload = "insert", payload
        return self
    def update(self, payload):
        self.action, self.payload = "update", payload
        return self
    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        if self.action == "insert":
            if self.name in self.db.fail_inserts:
                raise RuntimeError("simulated persistence failure")
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = [{"id": str(uuid4()), **deepcopy(row)} for row in payloads]
            self.db.inserts.append((self.name, deepcopy(payloads)))
            rows.extend(saved)
            return SimpleNamespace(data=deepcopy(saved))
        selected = [row for row in rows if all(fn(row) for fn in self.filters)]
        if self.action == "update":
            for row in selected:
                row.update(self.payload)
            self.db.updates.append((self.name, deepcopy(self.payload)))
            return SimpleNamespace(data=deepcopy(selected))
        if self.sort_key:
            key, reverse = self.sort_key
            selected.sort(key=lambda row: row.get(key) or "", reverse=reverse)
        if self.span:
            start, end = self.span
            selected = selected[start:end + 1]
        if self.max_rows is not None:
            selected = selected[:self.max_rows]
        selected = selected[:self.db.cap]
        return SimpleNamespace(data=deepcopy(selected[0] if selected and self.single_row else None if self.single_row else selected))


class Database:
    def __init__(self, tables=None, cap=1000):
        self.tables = deepcopy(tables or {})
        self.cap = cap
        self.pages, self.inserts, self.updates = [], [], []
        self.fail_inserts = set()
    def table(self, name): return Table(self, name)


class FakeSMS:
    _provider = "twilio"
    sends = []
    result = True
    dry_run = False
    def send(self, message, to_number):
        self.sends.append((message, to_number))
        message.a2p_provider = "twilio:dry-run" if self.dry_run else "twilio"
        return self.result


@pytest.fixture
def sms(monkeypatch):
    FakeSMS.sends = []
    FakeSMS.result = True
    FakeSMS.dry_run = False
    monkeypatch.setattr("tools.sms_client.SMSClient", FakeSMS)
    monkeypatch.setattr(marketing_api, "SMSClient", FakeSMS)
    return FakeSMS


def buyer_row(**kwargs):
    return {"id": str(uuid4()), "first_name": "Test", "last_name": "Buyer", "phone": "+12145550100", "sms_opt_in": True, "active": True, **kwargs}


@pytest.mark.asyncio
@pytest.mark.parametrize("sent,dry_run,expected", [(True, False, "sent_count"), (False, False, "failed_count"), (True, True, "dry_run_count")])
async def test_buyer_sms_uses_real_client_contract_and_reports_delivery(monkeypatch, sms, sent, dry_run, expected):
    buyer = buyer_row()
    db = Database({"buyers": [buyer]})
    monkeypatch.setattr(buyers_api, "_get_supabase", lambda: db)
    sms.result, sms.dry_run = sent, dry_run
    background = BackgroundTasks()
    result = await buyers_api.send_sms_blast(buyers_api.OutreachRequest(buyer_ids=[buyer["id"], buyer["id"]]), background)
    assert result[expected] == 1
    assert result["recipient_count"] == 1
    assert len(sms.sends) == 1
    assert not background.tasks
    message, phone = sms.sends[0]
    assert str(message.lead_id) == buyer["id"]
    assert phone == buyer["phone"]
    assert "Reply STOP to opt out." in message.body
    assert bool(db.updates) is (sent and not dry_run)


@pytest.mark.asyncio
async def test_buyer_sms_skips_opt_out_inactive_and_shared_suppression(monkeypatch, sms):
    buyers = [buyer_row(sms_opt_in=False), buyer_row(active=False), buyer_row()]
    db = Database({"buyers": buyers, "dnc_registry": [{"id": "suppressed", "phone_number": "2145550100"}]})
    monkeypatch.setattr(buyers_api, "_get_supabase", lambda: db)
    result = await buyers_api.send_sms_blast(buyers_api.OutreachRequest(buyer_ids=[b["id"] for b in buyers]), BackgroundTasks())
    assert result["skipped_count"] == 3
    assert not sms.sends


@pytest.mark.asyncio
async def test_buyer_sms_requires_database_before_reporting_success(monkeypatch, sms):
    monkeypatch.setattr(buyers_api, "_get_supabase", lambda: None)
    with pytest.raises(HTTPException) as exc:
        await buyers_api.send_sms_blast(buyers_api.OutreachRequest(buyer_ids=[str(uuid4())]), BackgroundTasks())
    assert exc.value.status_code == 503
    assert not sms.sends


def warm_row(**kwargs):
    return {"id": str(uuid4()), "owner_first_name": "Jane", "owner_phone_1": "+12145550100", "property_address": "123 Main St", "status": "qualified_warm", "dnc": False, "ai_calling_paused": False, **kwargs}


@pytest.mark.asyncio
async def test_warm_sms_uses_selected_supabase_leads_and_latest_qualification(monkeypatch, sms):
    eligible, dnc, paused, cold, suppressed = [warm_row(), warm_row(dnc=True), warm_row(ai_calling_paused=True), warm_row(), warm_row()]
    rows = [eligible, dnc, paused, cold, suppressed]
    db = Database({"leads": rows, "qualification_results": [
        {"lead_id": cold["id"], "classification": "COLD", "created_at": "2026-02"},
        {"lead_id": cold["id"], "classification": "WARM", "created_at": "2026-01"},
    ], "dnc_registry": [{"id": "stop", "lead_id": suppressed["id"]}]})
    monkeypatch.setattr(marketing_api, "get_supabase_client", lambda: db)
    result = await marketing_api.bulk_sms_warm(marketing_api.BulkSMSRequest(lead_ids=[row["id"] for row in rows]))
    assert result["sent_count"] == 1
    assert result["skipped_count"] == 4
    assert str(sms.sends[0][0].lead_id) == eligible["id"]
    assert "Jane" in sms.sends[0][0].body
    assert "123 Main St" in sms.sends[0][0].body


@pytest.mark.asyncio
async def test_warm_sms_log_failure_preserves_sent_count(monkeypatch, sms):
    row = warm_row()
    db = Database({"leads": [row]})
    db.fail_inserts.add("outreach_activity")
    monkeypatch.setattr(marketing_api, "get_supabase_client", lambda: db)
    result = await marketing_api.bulk_sms_warm(marketing_api.BulkSMSRequest(lead_ids=[row["id"]]))
    assert result["sent_count"] == 1
    assert result["failed_count"] == 0
    assert result["log_failed_count"] == 1
    assert result["status"] == "partial"


@pytest.mark.parametrize("template", ["Hi {unknown}", "Hi {first_name.__class__}", "Hi {address", "Hi {first_name!r}"])
def test_warm_sms_rejects_bad_template_before_sending(template):
    with pytest.raises(ValueError):
        marketing_api.BulkSMSRequest(lead_ids=[str(uuid4())], template=template)


@pytest.mark.asyncio
async def test_form_persists_supported_qualification_without_missing_agent_methods(monkeypatch, caplog):
    db = Database()
    monkeypatch.setattr(lead_forms_api, "_get_supabase", lambda: db)
    monkeypatch.setattr(lead_forms_api, "_send_lead_pipeline_sms", lambda **kwargs: None)
    monkeypatch.setattr(lead_forms_api, "_send_hot_lead_notification", lambda *args: None)
    answers = {"property_address": "123 Main St, Dallas, TX 75201", "motivation": "inherited", "timeline": "asap", "condition": "major_repairs", "occupancy": "vacant"}
    scores = lead_forms_api._compute_scores_from_answers(answers)
    await lead_forms_api._process_form_submission({}, answers, scores, None, None)
    row = db.tables["leads"][0]
    total = sum(scores[k] for k in scores if k.startswith("score_"))
    classification = "hot" if total >= 13 else "warm" if total >= 8 else "cold"
    assert row["status"] == f"qualified_{classification}"
    assert row["precision_tier"] == {"hot": 1, "warm": 2, "cold": 3}[classification]
    assert "Form-answer qualification" in row["ai_qualification_summary"]
    assert "neutral defaults pending verification" in row["ai_qualification_summary"]
    assert "agent failed" not in caplog.text


def test_import_finds_existing_row_beyond_postgrest_cap(monkeypatch):
    rows = [{"id": f"lead-{i:04d}", "property_address": f"{i} Main Street", "city": "Dallas", "state": "TX"} for i in range(1002)]
    db = Database({"leads": rows}, cap=500)
    monkeypatch.setattr("tools.crm.get_supabase_client", lambda: db)
    result = api.import_master_list(api.ImportMasterListRequest(rows=[api.ImportLeadRow(property_address="1001 Main St", city="dallas", zip_code="75201")], score_with_claude=False))
    assert result["updated"] == 1
    assert result["imported"] == 0
    assert len(db.tables["leads"]) == 1002
    assert [start for start, end in db.pages] == [0, 500, 1000, 1002]


def test_import_keeps_same_street_in_different_cities_separate(monkeypatch):
    db = Database()
    monkeypatch.setattr("tools.crm.get_supabase_client", lambda: db)
    result = api.import_master_list(api.ImportMasterListRequest(rows=[
        api.ImportLeadRow(property_address="123 Main St", city="Dallas"),
        api.ImportLeadRow(property_address="123 Main Street", city="Houston"),
    ], score_with_claude=False))
    assert result["imported"] == 2
    assert {row["city"] for row in db.tables["leads"]} == {"Dallas", "Houston"}


def test_import_new_rows_use_bounded_bulk_inserts(monkeypatch):
    db = Database()
    monkeypatch.setattr("tools.crm.get_supabase_client", lambda: db)
    result = api.import_master_list(api.ImportMasterListRequest(rows=[api.ImportLeadRow(property_address=f"{i} Main St", city="Dallas") for i in range(501)], score_with_claude=False))
    assert result["imported"] == 501
    assert [len(rows) for table, rows in db.inserts] == [250, 250, 1]


def test_reimport_unchanged_records_does_not_write_each_row(monkeypatch):
    db = Database({"leads": [{"id": "existing", "property_address": "123 Main St", "city": "Dallas", "state": "TX", "status": "qualified_warm"}]})
    monkeypatch.setattr("tools.crm.get_supabase_client", lambda: db)
    result = api.import_master_list(api.ImportMasterListRequest(rows=[api.ImportLeadRow(property_address="123 Main St", city="Dallas")], score_with_claude=False))
    assert result["updated"] == 1
    assert db.updates == []
    assert db.tables["leads"][0]["status"] == "qualified_warm"


@pytest.mark.asyncio
@pytest.mark.parametrize("sent,configured,expected", [(True, True, "sent_count"), (False, True, "failed_count"), (True, False, "dry_run_count")])
async def test_buyer_email_preserves_reviewed_copy_and_delivery_results(monkeypatch, sent, configured, expected):
    buyer = buyer_row(email="buyer@example.test", email_opt_in=True)
    db = Database({"buyers": [buyer]})
    monkeypatch.setattr(buyers_api, "_get_supabase", lambda: db)
    deliveries = []
    class FakeEmail:
        _provider = "mailgun"
        _configured = configured
        def send(self, to_email, subject, body, html_body=None):
            deliveries.append((to_email, subject, body, html_body))
            return sent
    monkeypatch.setattr("tools.email_client.EmailClient", FakeEmail)
    background = BackgroundTasks()
    result = await buyers_api.send_email_blast(buyers_api.OutreachRequest(
        buyer_ids=[buyer["id"]], custom_subject="Edited property subject",
        custom_message="Reviewed <details>\nSecond line",
    ), background)
    assert result[expected] == 1
    assert len(deliveries) == 1
    assert deliveries[0][:3] == (buyer["email"], "Edited property subject", "Reviewed <details>\nSecond line")
    assert "&lt;details&gt;" in deliveries[0][3]
    assert "<br>" in deliveries[0][3]
    assert not background.tasks
    assert bool(db.updates) is (sent and configured)


@pytest.mark.asyncio
async def test_buyer_email_skips_opted_out_and_inactive(monkeypatch):
    buyers = [buyer_row(email="first@example.test", email_opt_in=False), buyer_row(email="second@example.test", email_opt_in=True, active=False)]
    db = Database({"buyers": buyers})
    monkeypatch.setattr(buyers_api, "_get_supabase", lambda: db)
    class FakeEmail:
        def send(self, *args, **kwargs): raise AssertionError("Must not send")
    monkeypatch.setattr("tools.email_client.EmailClient", FakeEmail)
    result = await buyers_api.send_email_blast(buyers_api.OutreachRequest(buyer_ids=[b["id"] for b in buyers]), BackgroundTasks())
    assert result["skipped_count"] == 2
