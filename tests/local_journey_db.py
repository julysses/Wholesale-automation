"""Small PostgREST-shaped adapter executing real SQL in the disposable database.

Only query construction is adapted. Production RPC bodies, transactions, claims,
constraints and triggers run in PostgreSQL. No application database RPC is mocked.
"""
import json
import os
from types import SimpleNamespace
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from psycopg2 import sql


class Database:
    def __init__(self):
        url = os.environ["SMS_TEST_ADMIN_URL"]
        parsed = urlparse(url)
        if parsed.hostname != "127.0.0.1" or parsed.path != "/wholesale_sms_test":
            raise RuntimeError("Disposable localhost database required")
        self.connection = psycopg2.connect(url)
        self.connection.autocommit = True

    def query(self, statement, params=()):
        with self.connection.cursor(cursor_factory=RealDictCursor) as c:
            c.execute(statement, [Json(v) if isinstance(v, (dict, list)) else v for v in params] if params else None)
            rows = c.fetchall() if c.description else []
            # PostgREST uses JSON strings for timestamps/UUIDs.
            return json.loads(json.dumps(rows, default=str))

    def table(self, name):
        return Table(self, name)

    def rpc(self, name, params):
        expression = sql.SQL(",").join(sql.SQL("{} => %s").format(sql.Identifier(k)) for k in params)
        def execute():
            rows = self.query(sql.SQL("SELECT * FROM public.{}({})").format(sql.Identifier(name), expression), list(params.values()))
            if rows and name in rows[0] and len(rows[0]) == 1:
                value = rows[0][name]
            else:
                value = rows
            return SimpleNamespace(data=value)
        return SimpleNamespace(execute=execute)


class Table:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters, self.ordering, self.bound = [], None, None
        self.action, self.payload, self.one, self.conflict = "select", None, False, None

    def select(self, *_): return self
    def eq(self, key, value): self.filters.append((key, "=", value)); return self
    def is_(self, key, value):
        assert value == "null"
        self.filters.append((key, "IS", None)); return self
    def in_(self, key, value): self.filters.append((key, "IN", value)); return self
    def order(self, key, desc=False): self.ordering = (key, desc); return self
    def limit(self, n): self.bound = int(n); return self
    def single(self): self.one = True; return self
    def insert(self, row): self.action, self.payload = "insert", row; return self
    def update(self, row): self.action, self.payload = "update", row; return self
    def upsert(self, row, on_conflict="id", ignore_duplicates=False):
        assert ignore_duplicates, "Journey adapter supports immutable insert-only upsert"
        self.insert(row); self.conflict = on_conflict; return self

    def execute(self):
        name, params = sql.Identifier("public", self.name), []
        where = []
        for key, op, value in self.filters:
            parts = key.split("->>")
            column = sql.Identifier(parts[0]) if len(parts) == 1 else sql.SQL("{}->>{}").format(sql.Identifier(parts[0]), sql.Literal(parts[1]))
            if op == "IS":
                where.append(sql.SQL("{} IS NULL").format(column))
            elif op == "IN":
                where.append(sql.SQL("{} IN ({})").format(column, sql.SQL(",").join(sql.Placeholder() for _ in value)))
                params.extend(value)
            else:
                where.append(sql.SQL("{} = %s").format(column)); params.append(value)
        suffix = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where) if where else sql.SQL("")
        if self.action == "select":
            statement = sql.SQL("SELECT * FROM {}").format(name) + suffix
            if self.ordering:
                statement += sql.SQL(" ORDER BY {} {}").format(sql.Identifier(self.ordering[0]), sql.SQL("DESC" if self.ordering[1] else "ASC"))
            if self.bound is not None: statement += sql.SQL(" LIMIT {}").format(sql.Literal(self.bound))
        elif self.action == "insert":
            statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(name,
                sql.SQL(",").join(map(sql.Identifier, self.payload)), sql.SQL(",").join(sql.Placeholder() for _ in self.payload))
            params = list(self.payload.values())
            if self.conflict: statement += sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(sql.Identifier(self.conflict))
            statement += sql.SQL(" RETURNING *")
        else:
            statement = sql.SQL("UPDATE {} SET {}").format(name,
                sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k in self.payload)) + suffix + sql.SQL(" RETURNING *")
            params = list(self.payload.values()) + params
        result = self.db.query(statement, params)
        return SimpleNamespace(data=(result[0] if result else None) if self.one else result)
