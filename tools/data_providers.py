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


# ── Government Data Providers ─────────────────────────────────────────────────

class CodeViolationCSVProvider(BaseDataProvider):
    """
    City code enforcement / unsafe structure CSV export.

    Expected columns (flexible — DataSourceAgent normalizes):
      address, owner_name, parcel_id, violation_type, violation_date,
      violation_status, owner_occupied, property_type, county, zip,
      ownership_years

    Sources:
      - City code enforcement departments
      - Municipal unsafe structure registries
      - Vacant building registries

    Blueprint criteria:
      code_violation_status = true
      violation_type = structural OR unsafe
      ownership_length >= 5
      property_type = single_family
      exclude MLS_active
    """

    name = "code_violation_csv"
    source_tag = "code_violation"

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
                row["_code_violation_status"] = "true"
                records.append(dict(row))

        logger.info(f"[{self.name}] Loaded {len(records)} code violation records from {file_path}")
        return records


class UtilityShutoffCSVProvider(BaseDataProvider):
    """
    Utility shutoff (electric / water / gas) CSV export.

    Expected columns (flexible):
      address, owner_name, parcel_id, utility_type, shutoff_date,
      owner_occupied, equity_percent, property_type, county, zip

    Sources:
      - Electric utility departments
      - Water departments
      - Gas utility providers

    Blueprint criteria:
      utility_shutoff_status = true
      owner_occupied = false
      equity >= 30
      property_type = single_family
      exclude MLS_active
    """

    name = "utility_shutoff_csv"
    source_tag = "utility_shutoff"

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
                row["_utility_shutoff_status"] = "true"
                records.append(dict(row))

        logger.info(f"[{self.name}] Loaded {len(records)} utility shutoff records from {file_path}")
        return records


class MunicipalLienCSVProvider(BaseDataProvider):
    """
    Municipal lien CSV export (county clerk / city finance / lien registry).

    Expected columns (flexible):
      address, owner_name, parcel_id, lien_type, lien_amount, lien_date,
      equity_percent, ownership_years, property_type, county, zip

    Sources:
      - County clerk lien filings
      - City finance departments
      - Municipal lien registries

    Blueprint criteria:
      municipal_lien_status = true
      lien_amount >= 1000
      equity >= 40
      ownership_length >= 5
      property_type = single_family
    """

    name = "municipal_lien_csv"
    source_tag = "municipal_lien"

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
                row["_municipal_lien_status"] = "true"
                records.append(dict(row))

        logger.info(f"[{self.name}] Loaded {len(records)} municipal lien records from {file_path}")
        return records


# ── Factory ───────────────────────────────────────────────────────────────────


class PublicDataProvider:
    """Convenience wrapper grouping all public/free providers."""

    tax_delinquent = TaxDelinquentCSVProvider()
    probate = ProbateCSVProvider()
    manual = ManualLeadProvider()


class DataProviderFactory:
    """Create the right provider by name."""

    _registry: dict[str, BaseDataProvider] = {
        "tax_delinquent_csv":  TaxDelinquentCSVProvider(),
        "probate_csv":         ProbateCSVProvider(),
        "manual":              ManualLeadProvider(),
        "propstream":          PropStreamProvider(),
        "batchleads":          BatchLeadsProvider(),
        # Government data sources (blueprint)
        "code_violation_csv":  CodeViolationCSVProvider(),
        "utility_shutoff_csv": UtilityShutoffCSVProvider(),
        "municipal_lien_csv":  MunicipalLienCSVProvider(),
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
