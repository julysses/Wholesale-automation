import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app


client = TestClient(app)


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeLeadTable:
    def __init__(self, db):
        self.db = db
        self._op = "select"
        self._payload = None
        self._eq = None

    def select(self, *_args, **_kwargs):
        self._op = "select"
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
        return self

    def execute(self):
        if self._op == "select":
            return FakeResponse([dict(row) for row in self.db.rows])
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
            lead_ids = []
            for marker in ('"lead_id": "existing-1"', '"lead_id": "new-1"'):
                if marker in user:
                    lead_ids.append(marker.split('"')[3])
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
