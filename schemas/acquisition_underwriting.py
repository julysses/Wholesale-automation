"""Explicit, provenance-bearing inputs for acquisition scenario calculations."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Assumption(StrictModel):
    value: Decimal | None = Field(default=None, ge=0, le=Decimal('1000000000000'),max_digits=15,decimal_places=2)
    source: str = Field(min_length=1, max_length=500)
    basis: Literal['estimate','source_reported']
    confidence: Literal['low','medium','high']
    as_of: date | None = None


class Rate(Assumption):
    value: Decimal | None = Field(default=None, ge=0, le=1,max_digits=9,decimal_places=8)


class PositiveRate(Assumption):
    value: Decimal | None = Field(default=None, gt=0, le=1,max_digits=9,decimal_places=8)


class Months(Assumption):
    value: Decimal | None = Field(default=None, ge=0, le=600,max_digits=7,decimal_places=4)


class Financing(StrictModel):
    principal: Assumption | None = None
    average_balance: Assumption | None = None
    annual_rate: Rate | None = None
    points_rate: Rate | None = None
    other_fees: Assumption | None = None

    @model_validator(mode='after')
    def balance_limit(self):
        if (self.principal and self.average_balance and self.principal.value is not None
                and self.average_balance.value is not None and self.average_balance.value > self.principal.value):
            raise ValueError('Average outstanding balance cannot exceed committed principal')
        return self


class Common(StrictModel):
    purchase_price: Assumption | None = None
    acquisition_closing: Assumption | None = None
    liens: Assumption | None = None
    holding_months: Months | None = None
    holding_monthly_ex_interest: Assumption | None = None
    financing: Financing = Field(default_factory=Financing)
    offer_floor_fraction: Rate | None = None


class Flip(Common):
    strategy: Literal['fix_and_flip']
    arv: Assumption | None = None
    repairs: Assumption | None = None
    contingency: Assumption | None = None
    selling_rate: Rate | None = None
    selling_fixed: Assumption | None = None
    target_profit: Assumption | None = None


class Development(Common):
    strategy: Literal['development']
    completed_value: Assumption | None = None
    hard_costs: Assumption | None = None
    soft_costs: Assumption | None = None
    infrastructure: Assumption | None = None
    permits: Assumption | None = None
    contingency: Assumption | None = None
    selling_rate: Rate | None = None
    selling_fixed: Assumption | None = None
    target_profit: Assumption | None = None


class Rental(Common):
    strategy: Literal['rental']
    market_value: Assumption | None = None
    repairs: Assumption | None = None
    contingency: Assumption | None = None
    monthly_rent: Assumption | None = None
    vacancy_rate: Rate | None = None
    property_tax_annual: Assumption | None = None
    insurance_annual: Assumption | None = None
    maintenance_annual: Assumption | None = None
    utilities_annual: Assumption | None = None
    hoa_annual: Assumption | None = None
    other_operating_annual: Assumption | None = None
    management_rate: Rate | None = None
    capital_reserve_annual: Assumption | None = None
    # Zero explicitly selects interest-only; nonzero means a fully amortizing
    # fixed-rate loan. Balloon/refinance assumptions require a separate version.
    amortization_months: int | None = Field(default=None, ge=0, le=600)
    target_cap_rate: PositiveRate | None = None
    target_cash_on_cash: PositiveRate | None = None


    @model_validator(mode='after')
    def supported_term(self):
        if self.amortization_months is not None and 0 < self.amortization_months < 12:
            raise ValueError('Use a cash-flow schedule for amortization shorter than one year')
        return self


BuyerCase = Annotated[Union[Flip,Development,Rental],Field(discriminator='strategy')]


class Assignment(StrictModel):
    strategy: Literal['wholesale']
    contract_price: Assumption | None = None
    end_buyer_price: Assumption | None = None
    assignment_expenses: Assumption | None = None
    target_net_fee: Assumption | None = None
    offer_floor_fraction: Rate | None = None
    buyer_case: BuyerCase

    @model_validator(mode='after')
    def same_buyer_price(self):
        price=self.buyer_case.purchase_price
        if (price and self.end_buyer_price and price.value is not None and self.end_buyer_price.value is not None
                and price.value != self.end_buyer_price.value):
            raise ValueError('Buyer scenario purchase price must equal proposed end buyer price')
        return self


Scenario = Annotated[Union[Flip,Development,Rental,Assignment],Field(discriminator='strategy')]


class UnderwritingPreview(StrictModel):
    cases: dict[Literal['base','downside','upside'],Scenario]
    uncertainties: list[Literal['title','liens','occupancy','valuation','repairs','ownership','zoning','financing']] = Field(
        default_factory=lambda:['title','liens','occupancy','valuation','repairs','ownership'],max_length=8)

    @model_validator(mode='after')
    def complete_case_set(self):
        if set(self.cases) != {'base','downside','upside'}:
            raise ValueError('Provide explicit base, downside and upside cases')
        if len({case.strategy for case in self.cases.values()}) != 1:
            raise ValueError('All cases must evaluate the same acquisition strategy')
        if len(set(self.uncertainties)) != len(self.uncertainties):
            raise ValueError('Duplicate uncertainty category')
        return self
