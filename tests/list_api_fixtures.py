"""Offer review access, exact acknowledgement and recovery contracts."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from web.app import app
from web import auth
from web.api import list_pipeline_api as offers

OPERATOR='00000000-0000-4000-8000-000000000001'
LEAD=str(uuid4())
@pytest.fixture
def setup(monkeypatch):
    db=MagicMock()
    db.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id=OPERATOR))
    rows=db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'admin'}])
    monkeypatch.setattr(auth,'get_supabase_client',lambda:db)
    monkeypatch.setattr(offers,'get_supabase_client',lambda:db)
    return TestClient(app),db,rows
