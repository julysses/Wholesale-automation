"""
Data provider layer — abstracts public and paid lead sources.

Design: tool-agnostic. Add a new provider by subclassing BaseDataProvider.
All providers return raw dicts; the DataSourceAgent normalizes them.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)


class BaseDataProvider(ABC):
    name: str = "base_provider"
    source_tag: str = "manual"

    @abstractmethod
    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return raw records as list of dicts."""
        ...


# ── Public / Free Providers ───────────────────────────────────────────────────


class TaxDelinquentCSVProvider(BaseDataProvider):
    """
    Load Texas county tax delinquent records from a local CSV file.
    Most Texas counties publish this data quarterly.

    Expected columns (flexible — DataSourceAgent normalizes):
    address, owner_name, parcel_id, delinquent_amount, county, zip
    """

    name = "tax_delinquent_csv"
    source_tag = "tax_delinquent"

    def fetch(self, file_path: str, **kwargs: Any) -> list[dict[str, Any]]:
        path = Path(file_path)
        if not path.exists():
            logger.error(f"[{self.name}] File not found: {file_path}")
            return []

        records: list[dict[str, Any]] = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_source_tag"] = self.source_tag
                records.append(dict(row))

        logger.info(f"[{self.name}] Loaded {len(records)} records from {file_path}")
        return records


class ProbateCSVProvider(BaseDataProvider):
    """Load probate filing records from a CSV export."""

    name = "probate_csv"
    source_tag = "probate"

    def fetch(self, file_path: str, **kwargs: Any) -> list[dict[str, Any]]:
        path = Path(file_path)
        if not path.exists():
            return []

        records: list[dict[str, Any]] = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_source_tag"] = self.source_tag
                records.append(dict(row))

        logger.info(f"[{self.name}] Loaded {len(records)} probate records")
        return records


class ManualLeadProvider(BaseDataProvider):
    """Accept a list of manually entered lead dicts."""

    name = "manual"
    source_tag = "manual"

    def fetch(self, records: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        for r in records:
            r.setdefault("_source_tag", self.source_tag)
        return records


# ── Paid Providers (stubbed — enable when API keys available) ─────────────────


class PropStreamProvider(BaseDataProvider):
    """PropStream API integration (stubbed)."""

    name = "propstream"
    source_tag = "propstream"

    def fetch(self, state: str = "TX", **kwargs: Any) -> list[dict[str, Any]]:
        if not settings.propstream_api_key:
            logger.warning(f"[{self.name}] API key not configured — returning empty")
            return []
        # TODO: implement real API call
        logger.info(f"[{self.name}] PropStream fetch would run here")
        return []


class BatchLeadsProvider(BaseDataProvider):
    """BatchLeads API integration (stubbed)."""

    name = "batchleads"
    source_tag = "batchleads"

    def fetch(self, list_id: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        if not settings.batchleads_api_key:
            logger.warning(f"[{self.name}] API key not configured — returning empty")
            return []
        # TODO: implement real API call
        logger.info(f"[{self.name}] BatchLeads fetch would run here")
        return []


# ── Factory ───────────────────────────────────────────────────────────────────


class PublicDataProvider:
    """Convenience wrapper grouping all public/free providers."""

    tax_delinquent = TaxDelinquentCSVProvider()
    probate = ProbateCSVProvider()
    manual = ManualLeadProvider()


class DataProviderFactory:
    """Create the right provider by name."""

    _registry: dict[str, BaseDataProvider] = {
        "tax_delinquent_csv": TaxDelinquentCSVProvider(),
        "probate_csv": ProbateCSVProvider(),
        "manual": ManualLeadProvider(),
        "propstream": PropStreamProvider(),
        "batchleads": BatchLeadsProvider(),
    }

    @classmethod
    def get(cls, name: str) -> BaseDataProvider:
        provider = cls._registry.get(name)
        if provider is None:
            raise ValueError(f"Unknown data provider: {name}. "
                             f"Available: {list(cls._registry.keys())}")
        return provider

    @classmethod
    def register(cls, provider: BaseDataProvider) -> None:
        cls._registry[provider.name] = provider
