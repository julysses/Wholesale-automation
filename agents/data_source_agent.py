"""Data Source Agent — ingests, normalizes, and tags raw property leads."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from config.prompts import SystemPrompts
from schemas.property import DataSource, NormalizedAddress, PropertyLead
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DataSourceAgent(BaseAgent):
    name = "data_source_agent"
    system_prompt = SystemPrompts.DATA_SOURCE

    def normalize_lead(self, raw_record: dict[str, Any], source: DataSource) -> PropertyLead:
        """
        Accept a raw dict from any data provider, use Claude to normalize it,
        and return a validated PropertyLead.
        """
        prompt = f"""
Normalize this raw property record into a clean PropertyLead.
Source: {source.value}

Raw record:
{json.dumps(raw_record, indent=2)}

Rules:
- Only accept Texas (TX) properties
- Normalize the address to street / city / state / zip / county
- Clean the owner name (proper case, strip noise)
- Assign source_confidence based on data completeness (0.0–1.0)
- Identify any signals present: tax_delinquent, probate_inherited, vacancy,
  code_violation, absentee_owner, high_equity
- If the record is clearly incomplete or suspicious, set flagged=true and explain flag_reason
- parcel_id may be empty string if not available
"""
        result = self._call_structured(prompt, PropertyLead)
        # Enforce source from caller, not from model hallucination
        result.source = source
        logger.info(f"[{self.name}] Normalized lead {result.id} from {source.value}")
        return result

    def ingest_batch(
        self, records: list[dict[str, Any]], source: DataSource
    ) -> tuple[list[PropertyLead], list[dict]]:
        """
        Process a list of raw records.
        Returns (successful_leads, failed_records).
        """
        good: list[PropertyLead] = []
        failed: list[dict] = []

        for record in records:
            try:
                lead = self.normalize_lead(record, source)
                good.append(lead)
            except Exception as exc:
                logger.warning(f"[{self.name}] Failed to normalize record: {exc}")
                failed.append({"record": record, "error": str(exc)})

        logger.info(
            f"[{self.name}] Ingested {len(good)} leads, {len(failed)} failed from {source.value}"
        )
        return good, failed

    def run(self, records: list[dict[str, Any]], source: DataSource) -> list[PropertyLead]:
        """Main entry: normalize and return all clean leads."""
        leads, _ = self.ingest_batch(records, source)
        return [lead for lead in leads if not lead.flagged]
