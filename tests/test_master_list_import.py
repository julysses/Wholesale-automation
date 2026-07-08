import json
import re
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app


client = TestClient(app)


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class FakeLeadTable:
    def __init__(self, db):
        self.db = db
        self._op = "select"
        self._payload = None
        self._eq = None
        self._filters = []
        self._limit = None

    def select(self, *_args, **kwargs):
        self._op = "select"
        self._count_exact = kwargs.get("count") == "exact"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, field, value):
        self._eq = (field, value)
        self._filters.append(("eq", field, value))
        return self

    def neq(self, field, value):
        self._filters.append(("neq", field, value))
        return self

    def is_(self, field, value):
        self._filters.append(("is", field, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def execute(self):
        if self._op == "select":
            rows = [dict(row) for row in self.db.rows]
            for op, field, value in self._filters:
                if op == "eq":
                    rows = [row for row in rows if row.get(field) == value]
                elif op == "neq":
                    rows = [row for row in rows if row.get(field) != value]
                elif op == "is" and value == "null":
                    rows = [row for row in rows if row.get(field) is None]
            count = len(rows)
            if self._limit is not None:
                rows = rows[: self._limit]
            return FakeResponse(rows, count=count)
        if self._op == "insert":
            row = {"id": f"new-{self.db.next_id}", **self._payload}
            self.db.next_id += 1
            self.db.rows.append(row)
            return FakeResponse([dict(row)])
        if self._op == "update":
            field, value = self._eq
            for row in self.db.rows:
                if row.get(field) == value:
                    row.update(self._payload)
                    self.db.updates.append((value, dict(self._payload)))
                    return FakeResponse([dict(row)])
            return FakeResponse([])
        raise AssertionError(f"Unexpected op {self._op}")


class FakeRpc:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def execute(self):
        self.db.rpcs.append(self.name)
        return FakeResponse([])


class FakeSupabase:
    def __init__(self, rows):
        self.rows = rows
        self.next_id = 1
        self.updates = []
        self.rpcs = []

    def table(self, name):
        assert name == "leads"
        return FakeLeadTable(self)

    def rpc(self, name):
        return FakeRpc(self, name)


class FakeClaude:
    class Messages:
        def create(self, **kwargs):
            user = kwargs["messages"][0]["content"]
            lead_ids = list(dict.fromkeys(
                lead_id
                for lead_id in re.findall(r'"lead_id":\s*"([^"]+)"', user)
                if not lead_id.startswith("<")
            ))
            payload = [
                {
                    "lead_id": lead_id,
                    "score_motivation": 3,
                    "score_timeline": 3,
                    "score_equity": 3,
                    "score_condition": 2,
                    "score_flexibility": 2,
                    "qualification_summary": "Strong consolidated lead.",
                    "recommended_next_action": "Call first.",
                }
                for lead_id in lead_ids
            ]
            return type(
                "Msg",
                (),
                {"content": [type("Content", (), {"text": json.dumps(payload)})()]},
            )()

    messages = Messages()


class FailingForLeadClaude:
    class Messages:
        def create(self, **kwargs):
            user = kwargs["messages"][0]["content"]
            if '"lead_id": "bad-lead"' in user:
                raise RuntimeError("Claude refused this row")
            lead_ids = list(dict.fromkeys(
                lead_id
                for lead_id in re.findall(r'"lead_id":\s*"([^"]+)"', user)
                if not lead_id.startswith("<")
            ))
            payload = [
                {
                    "lead_id": lead_id,
                    "score_motivation": 3,
                    "score_timeline": 3,
                    "score_equity": 3,
                    "score_condition": 2,
                    "score_flexibility": 2,
                    "qualification_summary": "Strong consolidated lead.",
                }
                for lead_id in lead_ids
            ]
            return type(
                "Msg",
                (),
                {"content": [type("Content", (), {"text": json.dumps(payload)})()]},
            )()

    messages = Messages()


def test_import_master_list_consolidates_updates_and_scores():
    fake_db = FakeSupabase([
        {
            "id": "existing-1",
            "property_address": "123 Main Street",
            "city": "Dallas",
            "state": "TX",
            "zip_code": "75201",
            "owner_first_name": "Jane",
            "owner_last_name": "Seller",
            "owner_phone_1": None,
            "source": "old_list",
            "status": "new",
        }
    ])

    rows = [
        {
            "property_address": "123 Main St.",
            "city": "Dallas",
            "state": "tx",
            "zip_code": "75201-1234",
            "owner_phone_1": "(214) 555-0100",
            "sources": ["tax delinquent"],
            "stack_count": 2,
        },
        {
            "property_address": "123 Main Street",
            "city": "Dallas",
            "state": "TX",
            "zip_code": "75201",
            "owner_email": "seller@example.com",
            "sources": ["vacant"],
            "stack_count": 2,
        },
        {
            "property_address": "500 New Ave",
            "city": "Dallas",
            "state": "TX",
            "zip_code": "75202",
            "sources": ["probate"],
            "stack_count": 1,
        },
    ]

    with patch("tools.crm.get_supabase_client", return_value=fake_db), patch(
        "web.api._get_client", return_value=FakeClaude()
    ):
        response = client.post("/api/ai/import-master-list", json={"rows": rows})

    assert response.status_code == 200
    data = response.json()
    assert data["consolidated_rows"] == 2
    assert data["updated"] == 1
    assert data["imported"] == 1
    assert data["scored"] == 2

    existing = next(row for row in fake_db.rows if row["id"] == "existing-1")
    assert existing["owner_phone_1"] == "2145550100"
    assert existing["owner_email"] == "seller@example.com"
    assert existing["source"] == "old_list | tax delinquent | vacant"
    assert existing["score_motivation"] == 3
    assert existing["precision_tier"] == 1

    inserted = next(row for row in fake_db.rows if row["id"] == "new-1")
    assert inserted["property_address"] == "500 New Ave"
    assert inserted["score_timeline"] == 3
    assert "recompute_priority_ranks" in fake_db.rpcs


def test_lead_scoring_status_uses_database_counts():
    fake_db = FakeSupabase([
        {"id": "lead-1", "property_address": "1 A St", "status": "qualified_hot", "score_motivation": 3},
        {"id": "lead-2", "property_address": "2 B St", "status": "qualified_warm", "score_motivation": 2},
        {"id": "lead-3", "property_address": "3 C St", "status": "new", "score_motivation": None},
    ])

    with patch("tools.crm.get_supabase_client", return_value=fake_db):
        response = client.get("/api/ai/lead-scoring-status")

    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "scored": 2,
        "unscored": 1,
        "failed": 0,
        "hot": 1,
        "warm": 1,
        "cold": 0,
        "complete": False,
    }


def test_score_unscored_leads_persists_scores_reason_and_progress():
    fake_db = FakeSupabase([
        {
            "id": "lead-1",
            "property_address": "1 A St",
            "city": "Dallas",
            "state": "TX",
            "status": "new",
            "score_motivation": None,
        },
        {
            "id": "lead-2",
            "property_address": "2 B St",
            "city": "Dallas",
            "state": "TX",
            "status": "qualified_warm",
            "score_motivation": 2,
        },
    ])

    with patch("tools.crm.get_supabase_client", return_value=fake_db), patch(
        "web.api._get_client", return_value=FakeClaude()
    ):
        response = client.post("/api/ai/score-unscored-leads", json={"batch_size": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    assert data["scored"] == 1
    assert data["progress"]["unscored"] == 0
    assert data["progress"]["failed"] == 0
    assert data["progress"]["hot"] == 1

    lead = next(row for row in fake_db.rows if row["id"] == "lead-1")
    assert lead["status"] == "qualified_hot"
    assert lead["score_motivation"] == 3
    assert lead["ai_qualification_summary"] == "Strong consolidated lead."
    assert lead["precision_tier"] == 1
    assert "recompute_priority_ranks" in fake_db.rpcs


def test_score_unscored_leads_quarantines_bad_leads_without_500():
    fake_db = FakeSupabase([
        {
            "id": "good-lead",
            "property_address": "1 A St",
            "city": "Dallas",
            "state": "TX",
            "status": "new",
            "score_motivation": None,
        },
        {
            "id": "bad-lead",
            "property_address": "2 B St",
            "city": "Dallas",
            "state": "TX",
            "status": "new",
            "score_motivation": None,
            "internal_notes": "existing note",
        },
    ])

    with patch("tools.crm.get_supabase_client", return_value=fake_db), patch(
        "web.api._get_client", return_value=FailingForLeadClaude()
    ):
        response = client.post("/api/ai/score-unscored-leads", json={"batch_size": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 2
    assert data["scored"] == 1
    assert data["failed"] == 1
    assert data["progress"]["unscored"] == 0
    assert data["progress"]["failed"] == 1

    good = next(row for row in fake_db.rows if row["id"] == "good-lead")
    bad = next(row for row in fake_db.rows if row["id"] == "bad-lead")
    assert good["status"] == "qualified_hot"
    assert good["score_motivation"] == 3
    assert bad["status"] == "scoring_error"
    assert bad["score_motivation"] is None
    assert "existing note" in bad["internal_notes"]
    assert "Claude scoring error" in bad["internal_notes"]
