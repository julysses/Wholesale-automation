"""Failure and response-cap contracts for operator buyer reads."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from web.api import buyers_api as api


class Pages:
    def __init__(self, rows, mode='normal'):
        self.rows, self.mode, self.offset = rows, mode, 0
        self.calls = []

    def range(self, start, end):
        self.offset = start
        self.calls.append((start, end))
        return self

    def execute(self):
        start = self.offset
        count = len(self.rows)
        rows = self.rows[start:start + 200]
        if self.mode == 'missing': count = None
        if self.mode == 'changed' and start: count += 1
        if self.mode == 'repeat' and start: rows = self.rows[:200]
        if self.mode == 'incomplete' and start: rows = []
        return SimpleNamespace(data=rows, count=count)


def test_capped_reads_include_all_1003_rows():
    rows = [{'id': str(n)} for n in range(1003)]
    pages = Pages(rows)
    assert api._read_all_confirmed(lambda: pages, 'Buyers') == rows
    assert [start for start, _ in pages.calls] == [0, 200, 400, 600, 800, 1000, 1003]


@pytest.mark.parametrize('mode', ['missing', 'changed', 'repeat', 'incomplete'])
def test_uncertain_reads_never_return_a_partial_dataset(mode):
    pages = Pages([{'id': str(n)} for n in range(1003)], mode)
    with pytest.raises(ValueError): api._read_all_confirmed(lambda: pages, 'Buyers')
    assert len(pages.calls) <= 2


def test_failed_history_is_explicit_not_empty(monkeypatch):
    query = Mock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.side_effect = RuntimeError('offline')
    monkeypatch.setattr(api, '_get_supabase', lambda: SimpleNamespace(table=lambda _: query))
    with pytest.raises(HTTPException) as error: api.get_buyer_transactions('buyer-A')
    assert error.value.status_code == 503
