import pytest
from fastapi.testclient import TestClient

from web.app import app
from web.auth import require_operator


@pytest.fixture(autouse=True)
def approved_operator():
    app.dependency_overrides[require_operator] = lambda: None
    yield
    app.dependency_overrides.pop(require_operator, None)


client = TestClient(app)


class Resp:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class Table:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload, self.f, self.lim = "select", None, [], None

    def select(self, *_a, **_k): self.op = "select"; return self
    def insert(self, p, **_k): self.op, self.payload = "insert", p; return self
    def update(self, p): self.op, self.payload = "update", p; return self
    def upsert(self, p, **_k): self.op, self.payload = "upsert", p; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.f.append(("eq", k, v)); return self
    def neq(self, k, v): self.f.append(("neq", k, v)); return self
    def gt(self, k, v): self.f.append(("gt", k, v)); return self
    def in_(self, k, v): self.f.append(("in", k, list(v))); return self
    def is_(self, k, v): self.f.append(("is", k, v)); return self
    def order(self, *_a, **_k): return self
    def limit(self, n): self.lim = n; return self

    def _match(self, rows):
        for op, k, v in self.f:
            if op == "eq": rows = [r for r in rows if r.get(k) == v]
            elif op == "neq": rows = [r for r in rows if r.get(k) != v]
            elif op == "gt": rows = [r for r in rows if str(r.get(k)) > str(v)]
            elif op == "in": rows = [r for r in rows if r.get(k) in v]
            elif op == "is" and v == "null": rows = [r for r in rows if r.get(k) is None]
        return rows

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        if self.op == "select":
            m = sorted(self._match([dict(r) for r in rows]), key=lambda r: str(r.get("id")))
            n = len(m)
            return Resp(m[: self.lim] if self.lim else m, count=n)
        if self.op == "insert":
            out = []
            for p in (self.payload if isinstance(self.payload, list) else [self.payload]):
                row = {"id": f"{self.name}-{len(rows) + 1}", **p}
                rows.append(row); out.append(dict(row))
            return Resp(out)
        if self.op == "update":
            for r in self._match(rows): r.update(self.payload)
            return Resp([])
        if self.op == "upsert":
            self.db.upserts += 1
            for p in self.payload:
                for r in rows:
                    if r["id"] == p["id"]: r.update(p)
            return Resp([])
        if self.op == "delete":
            doomed = {id(r) for r in self._match(rows)}
            rows[:] = [r for r in rows if id(r) not in doomed]
            return Resp([])


class DB:
    def __init__(self, tables):
        self.tables, self.upserts, self.rpcs = tables, 0, []

    def table(self, name): return Table(self, name)

    def rpc(self, name):
        self.rpcs.append(name)
        return type("R", (), {"execute": lambda s: Resp([])})()


def leads(n, **kw):
    return [{"id": f"l{i:04d}", "property_address": f"{i} Main St", "city": "Dallas",
             "status": "new", "score_motivation": None, **kw} for i in range(n)]


def test_rules_scoring_is_bulk_and_completes_backlog():
    db = DB({"leads": leads(1200, source="Tax Delinquent", property_type="SFR", sqft=1500,
                            bedrooms=3, year_built=1990, owner_phone_1="1")})
    from unittest.mock import patch
    with patch("web.api._supabase_or_503", return_value=db):
        first = client.post("/api/ai/score-unscored-leads", json={"batch_size": 1000}).json()
        second = client.post("/api/ai/score-unscored-leads", json={"batch_size": 1000}).json()
    assert first["processed"] == 1000 and second["processed"] == 200
    assert db.upserts == 3          # 500+500 then 200 — not one write per lead
    assert second["progress"]["unscored"] == 0
    assert all(r["status"].startswith("qualified_") for r in db.tables["leads"])
    assert "recompute_priority_ranks" in db.rpcs


def test_full_rescore_walks_table_once_instead_of_looping():
    db = DB({"leads": leads(30, score_motivation=2, status="qualified_warm")})
    from unittest.mock import patch
    with patch("web.api._supabase_or_503", return_value=db):
        r = client.post("/api/ai/score-unscored-leads", json={"rescore_existing": True}).json()
    assert r["processed"] == 30


def test_bad_engine_rejected():
    assert client.post("/api/ai/score-unscored-leads", json={"engine": "gpt"}).status_code == 400


def _lists_db():
    rows = leads(3, list_id="A") + [
        {"id": "w1", "property_address": "9 Worked", "city": "Dallas", "status": "contacted", "list_id": "A"},
    ] + leads(2, list_id="B")
    for i, r in enumerate(rows): r["id"] = r["id"] if r["id"] == "w1" else f"x{i}"
    return DB({"leads": rows, "lead_lists": [
        {"id": "A", "name": "Tax roll", "created_at": "2026-01-02", "row_count": 4},
        {"id": "B", "name": "Probate", "created_at": "2026-01-01", "row_count": 2},
    ]})


def test_delete_list_keeps_worked_leads_by_default():
    from unittest.mock import patch
    db = _lists_db()
    with patch("web.api.lists_api._supabase", return_value=db):
        out = client.delete("/api/lead-lists/A").json()
    assert out["deleted"] == 3 and out["kept_worked"] == 1 and out["list_removed"] is False
    assert [r["id"] for r in db.tables["leads"] if r["list_id"] == "A"] == ["w1"]
    assert sum(1 for r in db.tables["leads"] if r["list_id"] == "B") == 2   # other list untouched


def test_delete_list_include_worked_removes_everything_and_record():
    from unittest.mock import patch
    db = _lists_db()
    with patch("web.api.lists_api._supabase", return_value=db):
        out = client.delete("/api/lead-lists/A?include_worked=true").json()
    assert out["deleted"] == 4 and out["list_removed"] is True
    assert [l["id"] for l in db.tables["lead_lists"]] == ["B"]


def test_delete_unknown_list_404():
    from unittest.mock import patch
    with patch("web.api.lists_api._supabase", return_value=_lists_db()):
        assert client.delete("/api/lead-lists/nope").status_code == 404


def test_list_endpoint_reports_counts_and_rescore_works():
    from unittest.mock import patch
    db = _lists_db()
    with patch("web.api.lists_api._supabase", return_value=db):
        lists = client.get("/api/lead-lists").json()["lists"]
        assert lists[0]["name"] == "Tax roll" and lists[0]["lead_count"] == 4
        assert lists[0]["deletable_count"] == 3 and lists[0]["worked_count"] == 1
        assert client.post("/api/lead-lists/A/rescore").json()["processed"] == 4


def test_buyer_import_delete_removes_only_buyers_it_created():
    from unittest.mock import patch
    db = DB({
        "buyer_import_log": [{"id": "imp1", "filename": "deeds.csv"}, {"id": "imp2", "filename": "b.csv"}],
        "buyers": [{"id": "b1", "import_log_id": "imp1"}, {"id": "b2", "import_log_id": "imp1"},
                   {"id": "b3", "import_log_id": "imp2"}, {"id": "b4", "import_log_id": None}],
    })
    with patch("web.api.buyers_api._get_supabase", return_value=db):
        listing = client.get("/api/buyers/imports")
        assert {i["id"]: i["buyers_remaining"] for i in listing.json()["imports"]} == {"imp1": 2, "imp2": 1}
        out = client.delete("/api/buyers/imports/imp1").json()
        assert client.delete("/api/buyers/imports/missing").status_code == 404
    assert out["buyers_deleted"] == 2
    assert sorted(b["id"] for b in db.tables["buyers"]) == ["b3", "b4"]
    assert [l["id"] for l in db.tables["buyer_import_log"]] == ["imp2"]


def test_rules_scoring_keeps_paging_when_server_caps_rows_per_page():
    """PostgREST max-rows can return 100 rows for limit(1000); one request must still drain the batch."""
    class CappedTable(Table):
        def limit(self, n):
            self.lim = min(n, 100)
            return self

    class CappedDB(DB):
        def table(self, name):
            return CappedTable(self, name)

    from unittest.mock import patch
    db = CappedDB({"leads": leads(450)})
    with patch("web.api._supabase_or_503", return_value=db):
        r = client.post("/api/ai/score-unscored-leads", json={"batch_size": 1000}).json()
    assert r["processed"] == 450 and r["progress"]["unscored"] == 0


def test_scoring_uses_single_sql_call_and_falls_back_when_function_missing():
    from unittest.mock import patch

    class SqlDB(DB):
        def __init__(self, tables, fn_ok=True):
            super().__init__(tables)
            self.fn_ok, self.calls = fn_ok, []

        def rpc(self, name, params=None):
            self.calls.append((name, params))
            db = self

            class R:
                def execute(self_inner):
                    if name == "score_leads_rules":
                        if not db.fn_ok:
                            raise RuntimeError("function public.score_leads_rules does not exist")
                        for r in db.tables["leads"]:
                            r.update(score_motivation=2, status="qualified_warm")
                        return Resp({"scored": len(db.tables["leads"])})
                    return Resp([])
            return R()

    db = SqlDB({"leads": leads(40)})
    with patch("web.api._supabase_or_503", return_value=db):
        r = client.post("/api/ai/score-unscored-leads", json={}).json()
    assert r["scored"] == 40 and r["progress"]["unscored"] == 0
    assert [c[0] for c in db.calls].count("score_leads_rules") == 1 and db.upserts == 0

    db2 = SqlDB({"leads": leads(30)}, fn_ok=False)   # migration not applied -> API-side rules path
    with patch("web.api._supabase_or_503", return_value=db2):
        r2 = client.post("/api/ai/score-unscored-leads", json={}).json()
    assert r2["scored"] == 30 and db2.upserts >= 1


def test_cleanup_suggestions_and_apply_delete_only_returned_ids():
    from unittest.mock import patch

    class CleanDB(DB):
        def rpc(self, name, params=None):
            db = self

            class R:
                def execute(self_inner):
                    if name == "lead_cleanup_counts":
                        return Resp({"not_real_estate": 2, "duplicates": 1})
                    if name == "lead_cleanup_ids":
                        return Resp(["bpp1", "bpp2"] if params["p_rule"] == "not_real_estate" else [])
                    return Resp([])
            return R()

    rows = [{"id": i, "property_address": "x", "city": "y", "status": "new"} for i in ("bpp1", "bpp2", "keep")]
    db = CleanDB({"leads": rows})
    with patch("web.api.lists_api._supabase", return_value=db):
        s = client.get("/api/lead-lists/cleanup-suggestions").json()
        assert {r["id"]: r["count"] for r in s["rules"]}["not_real_estate"] == 2
        assert any("DNC" in h["who"] for h in s["hold"])
        out = client.post("/api/lead-lists/cleanup/not_real_estate").json()
        assert client.post("/api/lead-lists/cleanup/bogus").status_code == 404
    assert out["deleted"] == 2 and [r["id"] for r in db.tables["leads"]] == ["keep"]
