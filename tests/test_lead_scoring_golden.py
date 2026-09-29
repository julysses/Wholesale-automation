"""Golden cases taken from production rows and scored by the live SQL function
public.score_leads_rules. The Python engine must agree factor-for-factor so the
two implementations (bulk SQL, single-lead/fallback Python) cannot drift."""
import pytest

from tools.lead_scoring_engine import score_lead

PREFOR = "Property Export Collin+PreFor+July26"
TAX = "Collin_County_Delinquent_Tax_Roll"


def row(address, **kw):
    return {"id": "x", "property_address": address, "city": "Plano", **kw}


CASES = [
    ("prefor sfr fits buy-box -> HOT",
     row("2000 Pueblo Ct", source=PREFOR, property_type="Single Family Residential", owner_mailing_address="2000 Pueblo Ct",
         sqft=2053, bedrooms=3, year_built=2005, asking_price=464000, owner_phone_1="4406682519", owner_phone_2="4696440112",
         owner_email="a@b.com"), [3, 3, 2, 3, 3], "HOT"),
    ("prefor but oversized/pricey -> WARM",
     row("13568 Vineyard Ln", source=PREFOR, property_type="Single Family Residential", owner_mailing_address="13568 Vineyard Ln",
         sqft=4033, bedrooms=6, year_built=2020, asking_price=909000, owner_phone_1="6159433837", owner_email="a@b.com"),
     [3, 3, 2, 2, 2], "WARM"),
    ("business personal property is not real estate",
     row("6675 MEDITERRANEAN DR", source=TAX, property_type="Business Personal Property", owner_mailing_address="77 FELLOWSHIP LN"),
     [1, 1, 1, 1, 1], "COLD"),
    ("tax delinquent, owner-occupied",
     row("2406 HOGANS HL", source=TAX, property_type="Real Property", owner_mailing_address="2406 HOGANS HL"),
     [2, 2, 2, 2, 2], "WARM"),
    ("tax delinquent, PO box mailing = absentee",
     row("8763 BRIARGROVE LN", source=TAX, property_type="Real Property", owner_mailing_address="PO BOX 888"),
     [3, 2, 2, 2, 2], "WARM"),
    ("tax delinquent, absentee, 'Other' type has a narrow exit",
     row("3994 ADA CIR", source=TAX, property_type="Other", owner_mailing_address="2355 EDMONSON DR"),
     [3, 2, 2, 1, 2], "WARM"),
    ("no street number = unimproved land",
     row("COUNTY ROAD 904", source=TAX, property_type="Real Property", owner_mailing_address="10516 COUNTY ROAD 904"),
     [3, 2, 2, 1, 2], "WARM"),
    ("no distress signal, buy-box fit only",
     row("819 Ridgemont Dr", sqft=2226, bedrooms=4, asking_price=407000, owner_phone_1="4696673229"),
     [1, 1, 1, 3, 2], "COLD"),
    ("stacked on two pre-foreclosure lists",
     row("340 Daniel Dr", source=PREFOR + " | Property Export North+Dallas", property_type="Single Family Residential",
         owner_mailing_address="340 Daniel Dr", sqft=2748, bedrooms=4, year_built=1990, asking_price=692000,
         owner_phone_1="9724246749", owner_phone_2="9724224180", owner_email="d@e.com"),
     [3, 3, 2, 3, 3], "HOT"),
]


@pytest.mark.parametrize("name,lead,factors,tier", CASES, ids=[c[0] for c in CASES])
def test_python_engine_matches_production_sql(name, lead, factors, tier):
    r = score_lead(lead)
    assert [r.factors[k] for k in (
        "score_motivation", "score_timeline", "score_equity", "score_condition", "score_flexibility")] == factors
    assert r.tier == tier
