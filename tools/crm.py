"""
CRM Store — lightweight SQLite-backed persistence for leads, buyers, deals, and audit logs.
Uses SQLAlchemy Core for simplicity. Swap to Postgres by changing DATABASE_URL.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
    update,
)
from sqlalchemy.engine import Engine

from config.settings import settings
from schemas.buyer import BuyerProfile, BuyerQualification
from schemas.compliance import AuditLogEntry
from schemas.deal import Deal, UnderwritingReport
from schemas.property import PropertyLead

logger = logging.getLogger(__name__)


def get_supabase_client() -> Optional[Any]:
    """Return a Supabase client using service role key, or None if not configured."""
    url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    if not (url and key):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        logger.error(f"[CRM] Supabase init failed: {exc}")
        return None


metadata = MetaData()

leads_table = Table(
    "leads",
    metadata,
    Column("id", String, primary_key=True),
    Column("address_full", String),
    Column("owner_name", String),
    Column("source", String),
    Column("distress_score", Integer, nullable=True),
    Column("flagged", Boolean, default=False),
    Column("data", JSON),  # Full PropertyLead JSON
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

deals_table = Table(
    "deals",
    metadata,
    Column("id", String, primary_key=True),
    Column("lead_id", String),
    Column("status", String),
    Column("contract_price", Float, nullable=True),
    Column("assignment_fee", Float, nullable=True),
    Column("assigned_buyer_id", String, nullable=True),
    Column("data", JSON),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

buyers_table = Table(
    "buyers",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String),
    Column("company", String),
    Column("source", String),
    Column("reliability_score", Float, default=50.0),
    Column("disqualified", Boolean, default=False),
    Column("data", JSON),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

audit_log_table = Table(
    "audit_log",
    metadata,
    Column("id", String, primary_key=True),
    Column("timestamp", DateTime),
    Column("agent", String),
    Column("action", String),
    Column("entity_id", String, nullable=True),
    Column("entity_type", String),
    Column("status", String),
    Column("input_summary", Text),
    Column("output_summary", Text),
    Column("metadata", JSON),
)


class CRMStore:
    """Thin persistence layer for all agency data."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        url = database_url or settings.database_url
        self._engine: Engine = create_engine(url, echo=False)
        metadata.create_all(self._engine)
        logger.info(f"[CRM] Database initialized at {url}")

    # ── Leads ─────────────────────────────────────────────────────────────────

    def save_lead(self, lead: PropertyLead) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                leads_table.insert().prefix_with("OR REPLACE").values(
                    id=str(lead.id),
                    address_full=lead.address.full,
                    owner_name=lead.owner_name,
                    source=lead.source.value,
                    distress_score=lead.distress_score,
                    flagged=lead.flagged,
                    data=lead.model_dump(mode="json"),
                    created_at=lead.created_at,
                    updated_at=lead.updated_at,
                )
            )

    def get_lead(self, lead_id: str) -> Optional[dict[str, Any]]:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(leads_table).where(leads_table.c.id == lead_id)
            ).first()
            return dict(row._mapping) if row else None

    def get_all_leads(self) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(leads_table)).fetchall()
            return [dict(r._mapping) for r in rows]

    # ── Deals ─────────────────────────────────────────────────────────────────

    def save_deal(self, deal: Deal) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                deals_table.insert().prefix_with("OR REPLACE").values(
                    id=str(deal.id),
                    lead_id=str(deal.lead_id),
                    status=deal.status.value,
                    contract_price=deal.contract_price,
                    assignment_fee=deal.assignment_fee,
                    assigned_buyer_id=(
                        str(deal.assigned_buyer_id) if deal.assigned_buyer_id else None
                    ),
                    data=deal.model_dump(mode="json"),
                    created_at=deal.created_at,
                    updated_at=deal.updated_at,
                )
            )

    def get_active_deals(self) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(deals_table).where(
                    deals_table.c.status.notin_(["dead", "closed"])
                )
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    # ── Buyers ────────────────────────────────────────────────────────────────

    def save_buyer(
        self, profile: BuyerProfile, qual: Optional[BuyerQualification] = None
    ) -> None:
        data = profile.model_dump(mode="json")
        if qual:
            data["qualification"] = qual.model_dump(mode="json")

        with self._engine.begin() as conn:
            conn.execute(
                buyers_table.insert().prefix_with("OR REPLACE").values(
                    id=str(profile.id),
                    name=profile.name,
                    company=profile.company,
                    source=profile.source.value,
                    reliability_score=qual.reliability_score if qual else 50.0,
                    disqualified=qual.disqualified if qual else False,
                    data=data,
                    created_at=profile.created_at,
                    updated_at=profile.updated_at,
                )
            )

    def get_active_buyers(self) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(buyers_table).where(buyers_table.c.disqualified == False)  # noqa: E712
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def save_audit_entry(self, entry: AuditLogEntry) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                audit_log_table.insert().values(
                    id=str(entry.id),
                    timestamp=entry.timestamp,
                    agent=entry.agent,
                    action=entry.action,
                    entity_id=str(entry.entity_id) if entry.entity_id else None,
                    entity_type=entry.entity_type,
                    status=entry.status,
                    input_summary=entry.input_summary,
                    output_summary=entry.output_summary,
                    metadata=entry.metadata,
                )
            )

    def get_audit_log(
        self,
        agent: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            query = select(audit_log_table).order_by(
                audit_log_table.c.timestamp.desc()
            ).limit(limit)
            if agent:
                query = query.where(audit_log_table.c.agent == agent)
            rows = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in rows]
