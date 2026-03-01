"""
Data provider tests — file-based and manual providers only (no API keys needed).
"""

import csv
import pytest
import tempfile
from pathlib import Path

from tools.data_providers import (
    DataProviderFactory,
    ManualLeadProvider,
    TaxDelinquentCSVProvider,
)


class TestManualLeadProvider:
    def test_returns_records_with_source_tag(self):
        provider = ManualLeadProvider()
        records = [
            {"address": "123 Main St, Dallas, TX 75201", "owner": "John Doe"},
            {"address": "456 Oak Ave, Houston, TX 77001", "owner": "Jane Smith"},
        ]
        result = provider.fetch(records=records)
        assert len(result) == 2
        assert all(r["_source_tag"] == "manual" for r in result)

    def test_preserves_existing_source_tag(self):
        provider = ManualLeadProvider()
        records = [{"address": "789 Pine Rd", "_source_tag": "custom"}]
        result = provider.fetch(records=records)
        assert result[0]["_source_tag"] == "custom"


class TestTaxDelinquentCSVProvider:
    def test_loads_csv_file(self, tmp_path):
        csv_file = tmp_path / "tax_delinquent.csv"
        rows = [
            {"address": "100 Elm St, Dallas, TX 75201", "owner_name": "Alice Brown", "delinquent_amount": "3500"},
            {"address": "200 Birch Blvd, Houston, TX 77002", "owner_name": "Bob Wilson", "delinquent_amount": "7800"},
        ]
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        provider = TaxDelinquentCSVProvider()
        result = provider.fetch(file_path=str(csv_file))

        assert len(result) == 2
        assert all(r["_source_tag"] == "tax_delinquent" for r in result)
        assert result[0]["owner_name"] == "Alice Brown"

    def test_returns_empty_for_missing_file(self):
        provider = TaxDelinquentCSVProvider()
        result = provider.fetch(file_path="/nonexistent/path/file.csv")
        assert result == []


class TestDataProviderFactory:
    def test_get_known_providers(self):
        for name in ["tax_delinquent_csv", "probate_csv", "manual", "propstream", "batchleads"]:
            provider = DataProviderFactory.get(name)
            assert provider is not None

    def test_raises_for_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown data provider"):
            DataProviderFactory.get("nonexistent_provider")

    def test_register_custom_provider(self):
        from tools.data_providers import BaseDataProvider

        class CustomProvider(BaseDataProvider):
            name = "custom_test"
            source_tag = "custom"

            def fetch(self, **kwargs):
                return [{"custom": True}]

        DataProviderFactory.register(CustomProvider())
        provider = DataProviderFactory.get("custom_test")
        assert provider.fetch() == [{"custom": True}]
