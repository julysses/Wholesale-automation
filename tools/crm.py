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
    func,
    select,
    update,
)
from sqlalchemy.engine import Engine

from config.settings import settings
from schemas.buyer import BuyerProfile, BuyerQualification
from schemas.compliance import AuditLogEntry, OptOutRecord
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

opt_outs_table = Table(
    "opt_outs",
    metadata,
    Column("id", String, primary_key=True),
    Column("lead_id", String),
    Column("phone_or_email", String, nullable=False),
    Column("opt_out_keyword", String, nullable=False),
    Column("channel", String),
    Column("received_at", DateTime),
    Column("suppressed_at", DateTime),
    Column("inbound_text", Text),
)


class CRMStore:
    """Thin persistence layer for all agency data."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        url = database_url or settings.database_url
        self._engine: Engine = create_engine(url, echo=False)
        metadata.create_all(self._engine)
        logger.info(f"[CRM] Database initialized at {url}")

    # ── Leads ─────────────────────────────────────────────────────────────────

    def find_lead_by_address(self, address_full: str) -> Optional[dict[str, Any]]:
        """Return an existing lead row matching the given address (case/whitespace
        insensitive), or None. Used for deduplication on import."""
        if not address_full or not address_full.strip():
            return None
        norm = address_full.strip().lower()
        with self._engine.connect() as conn:
            row = conn.execute(
                select(leads_table).where(
                    func.lower(func.trim(leads_table.c.address_full)) == norm
                )
            ).first()
            return dict(row._mapping) if row else None

    def save_lead(self, lead: PropertyLead, dedup: bool = False) -> bool:
        """Persist a lead.

        When ``dedup`` is True and a lead with the same address already exists, the
        existing record is updated in place (its id and created_at are preserved)
        instead of creating a duplicate row.

        Returns True if a new lead was inserted, False if an existing one was updated.
        """
        is_new = True
        lead_id = str(lead.id)
        created_at = lead.created_at
        data = lead.model_dump(mode="json")

        if dedup:
            existing = self.find_lead_by_address(lead.address.full)
            if existing and str(existing.get("id")) != lead_id:
                lead_id = str(existing["id"])
                created_at = existing.get("created_at") or created_at
                data["id"] = lead_id   # keep embedded JSON id aligned with the row id
                is_new = False

        with self._engine.begin() as conn:
            conn.execute(
                leads_table.insert().prefix_with("OR REPLACE").values(
                    id=lead_id,
                    address_full=lead.address.full,
                    owner_name=lead.owner_name,
                    source=lead.source.value,
                    distress_score=lead.distress_score,
                    flagged=lead.flagged,
                    data=data,
                    created_at=created_at,
                    updated_at=lead.updated_at,
                )
            )
        return is_new

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

    # ── Opt-Out Suppression ──────────────────────────────────────────────────

    def save_opt_out_record(self, record: OptOutRecord) -> None:
        """Persist an immutable opt-out record for future suppression checks."""
        with self._engine.begin() as conn:
            conn.execute(
                opt_outs_table.insert().values(
                    id=str(record.id),
                    lead_id=str(record.lead_id),
                    phone_or_email=record.phone_or_email.strip().lower(),
                    opt_out_keyword=record.opt_out_keyword,
                    channel=record.channel,
                    received_at=record.received_at,
                    suppressed_at=record.suppressed_at,
                    inbound_text=record.inbound_text,
                )
            )

    def is_contact_suppressed(self, contact_identifier: str) -> bool:
        """Return True when a phone or email has an opt-out record."""
        normalized = contact_identifier.strip().lower()
        if not normalized:
            return False
        with self._engine.connect() as conn:
            row = conn.execute(
                select(opt_outs_table.c.id)
                .where(func.lower(opt_outs_table.c.phone_or_email) == normalized)
                .limit(1)
            ).first()
            return row is not None

    def get_opt_out_records(
        self,
        contact_identifier: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return persisted opt-out records, newest first."""
        with self._engine.connect() as conn:
            query = select(opt_outs_table).order_by(
                opt_outs_table.c.received_at.desc()
            ).limit(limit)
            if contact_identifier:
                query = query.where(
                    func.lower(opt_outs_table.c.phone_or_email)
                    == contact_identifier.strip().lower()
                )
            rows = conn.execute(query).fetchall()
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
