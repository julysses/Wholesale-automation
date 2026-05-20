"""Regression tests for non-blocking HOT lead automation scheduling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import web.api.webhooks as webhooks


@pytest.mark.asyncio
async def test_hot_lead_automation_scheduler_does_not_await_work(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    completed = False

    async def slow_hot_automation(**kwargs):
        nonlocal completed
        started.set()
        await release.wait()
        completed = True

    monkeypatch.setattr(webhooks, "_trigger_hot_lead_automation", slow_hot_automation)

    webhooks._schedule_hot_lead_automation(
        sb=object(),
        lead_id="lead_123",
        call_id="call_123",
        address="100 Test Ave",
        owner="Test Owner",
        qual=SimpleNamespace(),
        arv=None,
        mao=None,
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    assert completed is False

    release.set()
    await asyncio.sleep(0)
    assert completed is True
