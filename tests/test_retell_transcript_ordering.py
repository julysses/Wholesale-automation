"""Regression tests for Retell realtime transcript chunk ordering."""

from __future__ import annotations

from typing import Any

import pytest

import web.api.webhooks as webhooks


class FakeResponse:
    def __init__(self, data: Any = None) -> None:
        self.data = data


class FakeTable:
    def __init__(self, store: dict[str, dict[str, Any]], name: str) -> None:
        self.store = store
        self.name = name
        self.action = ""
        self.payload: dict[str, Any] = {}
        self.filters: dict[str, Any] = {}

    def select(self, *_args: Any, **_kwargs: Any) -> "FakeTable":
        self.action = "select"
        return self

    def eq(self, key: str, value: Any) -> "FakeTable":
        self.filters[key] = value
        return self

    def single(self) -> "FakeTable":
        return self

    def upsert(self, payload: dict[str, Any], **_kwargs: Any) -> "FakeTable":
        self.action = "upsert"
        self.payload = payload
        return self

    def execute(self) -> FakeResponse:
        table = self.store.setdefault(self.name, {})
        if self.action == "upsert":
            table[self.payload["call_id"]] = self.payload
            return FakeResponse(self.payload)

        call_id = self.filters.get("call_id")
        return FakeResponse(table.get(call_id))


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {"call_transcripts": {}}

    def table(self, name: str) -> FakeTable:
        return FakeTable(self.store, name)


def _chunk(sequence: int, role: str, content: str, timestamp: int) -> dict[str, Any]:
    return {
        "sequence_num": sequence,
        "transcript": [{
            "role": role,
            "content": content,
            "words": [{"start": timestamp}],
        }],
    }


def test_merge_transcript_chunks_sorts_by_sequence_then_timestamp():
    late = webhooks._normalize_transcript_chunk(
        _chunk(2, "user", "I need to sell this month.", 2000)
    )
    early = webhooks._normalize_transcript_chunk(
        _chunk(1, "agent", "Would you consider an offer?", 1000)
    )

    merged = webhooks._merge_transcript_chunks([late], [early])

    assert [chunk["sequence_num"] for chunk in merged] == [1, 2]
    assert webhooks.transcript_to_text(webhooks._flatten_transcript_chunks(merged)) == (
        "Agent: Would you consider an offer?\n"
        "Seller: I need to sell this month."
    )


@pytest.mark.asyncio
async def test_retell_transcript_chunk_upsert_reassembles_out_of_order_chunks(monkeypatch):
    sb = FakeSupabase()
    monkeypatch.setattr(webhooks, "_get_supabase", lambda: sb)

    await webhooks._retell_transcript_chunk(
        "call_123",
        "lead_123",
        _chunk(2, "user", "I need to sell this month.", 2000),
    )
    await webhooks._retell_transcript_chunk(
        "call_123",
        "lead_123",
        _chunk(1, "agent", "Would you consider an offer?", 1000),
    )

    stored = sb.store["call_transcripts"]["call_123"]

    assert stored["raw_transcript"] == (
        "Agent: Would you consider an offer?\n"
        "Seller: I need to sell this month."
    )
    assert stored["formatted"]["source"] == "retell_realtime_chunks"
    assert [chunk["sequence_num"] for chunk in stored["formatted"]["chunks"]] == [1, 2]


def test_final_transcript_payload_falls_back_to_ordered_realtime_chunks():
    sb = FakeSupabase()
    chunks = webhooks._merge_transcript_chunks(
        [webhooks._normalize_transcript_chunk(_chunk(2, "user", "Yes, soon.", 2000))],
        [webhooks._normalize_transcript_chunk(_chunk(1, "agent", "Are you selling?", 1000))],
    )
    sb.store["call_transcripts"]["call_123"] = {
        "call_id": "call_123",
        "formatted": {
            "source": "retell_realtime_chunks",
            "chunks": chunks,
        },
    }

    payload = webhooks._build_retell_transcript_payload(
        sb,
        "call_123",
        "lead_123",
        None,
    )

    assert payload["raw_transcript"] == "Agent: Are you selling?\nSeller: Yes, soon."
    assert payload["formatted"]["source"] == "retell_realtime_chunks"
    assert [turn["role"] for turn in payload["formatted"]["turns"]] == ["agent", "user"]
