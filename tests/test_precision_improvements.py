import pytest
from unittest.mock import MagicMock, patch
from tools.batchdata_adapter import BatchDataAdapter, CompsResult, PropertyDetails
from agents.deal_analyzer_agent import DealAnalyzerAgent
from fastapi.testclient import TestClient
from web.app import app
from web.api.fb_ads_api import ReviewCopyRequest
from tools.crm import CRMStore
from schemas.property import PropertyLead, NormalizedAddress, DataSource

client = TestClient(app)

def test_review_copy_request_accepts_copy_alias():
    body = ReviewCopyRequest(copy="Need help selling?", segment="probate")

    assert body.ad_copy == "Need help selling?"
    assert body.segment == "probate"

def test_batchdata_get_property_details_mock():
    adapter = BatchDataAdapter()
    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "results": [
                {
                    "estimatedValue": 250000,
                    "estimatedEquityPercent": 65,
                    "bedrooms": 4,
                    "bathrooms": 2.5,
                    "buildingSize": 2100,
                    "yearBuilt": 1995,
                    "lotSizeSqft": 7500,
                    "propertyType": "Single Family"
                }
            ]
        }
        
        # Ensure we have an API key for the test
        adapter._api_key = "test_key"
        
        details = adapter.get_property_details("123 Main St", "Austin", "TX", "78704")
        
        assert details.success is True
        assert details.estimated_value == 250000
        assert details.beds == 4
        assert details.sqft == 2100

def test_deal_analyzer_uses_batchdata():
    agent = DealAnalyzerAgent()
    # Mock BatchDataAdapter
    agent.batchdata = MagicMock()
    agent.batchdata.get_comparable_sales.return_value = CompsResult(
        lead_id="test_lead",
        success=False,
    )
    agent.batchdata.get_property_details.return_value = PropertyDetails(
        lead_id="test_lead",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78704",
        estimated_value=300000,
        success=True,
        sqft=2000,
        beds=3,
        year_built=2000
    )
    
    analysis = agent.analyze(
        lead_id="test_lead",
        property_address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78704"
    )
    
    # ARV mid should be 300,000 as per mock
    assert analysis.arv.mid == 300000
    assert "BatchData AVM estimate" in analysis.arv.notes

def test_rescore_leads_endpoint():
    crm = CRMStore()
    # 1. Create a lead and save it
    lead = PropertyLead(
        address=NormalizedAddress(street="100 Test Ave", city="Dallas", zip_code="75201"),
        owner_name="Test Owner",
        source=DataSource.MANUAL,
        is_vacant=True,
        is_absentee=True
    )
    # Ensure it's not currently scored
    lead.seller_score = None
    crm.save_lead(lead)
    
    # 2. Call the rescore endpoint
    from web.auth import require_operator
    from web.app import app
    app.dependency_overrides[require_operator] = lambda: None
    try:
        response = client.post("/api/leads/rescore")
    finally:
        app.dependency_overrides.pop(require_operator, None)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["count"] >= 1
    
    # 3. Verify lead is now scored in DB
    raw_lead = crm.get_lead(str(lead.id))
    assert raw_lead["distress_score"] is not None
    
    # Cleanup
    # (Actually CRMStore uses settings.database_url, so it might modify the real dev DB)
    # Ideally tests should use an in-memory DB.
