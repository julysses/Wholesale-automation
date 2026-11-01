"""Draft term inputs with source precision; never verified facts or execution authority."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

TermName = Literal['purchase_price', 'earnest_money', 'assignment', 'effective', 'inspection_deadline', 'closing_deadline']
MAX_CENTS = 9007199254740991  # Largest exact integer supported by the browser transport.


class Exact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ContractDateTerm(Exact):
    precision: Literal['unknown', 'date', 'instant']
    calendar_date: date | None = None
    instant: AwareDatetime | None = None

    @field_validator('calendar_date', mode='before')
    @classmethod
    def exact_date(cls, value):
        if value is None or type(value) is date:
            return value
        if isinstance(value, str) and len(value) == 10 and date.fromisoformat(value).isoformat() == value:
            return value
        raise ValueError('Explicit calendar date required; no inferred cutoff time')

    @field_validator('instant', mode='before')
    @classmethod
    def explicit_instant(cls, value):
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str) and 'T' in value:
            return value
        raise ValueError('Explicit timestamp with timezone required')

    @model_validator(mode='after')
    def preserve_precision(self):
        valid = {'unknown': self.calendar_date is None and self.instant is None,
                 'date': self.calendar_date is not None and self.instant is None,
                 'instant': self.instant is not None and self.calendar_date is None}
        if not valid[self.precision]:
            raise ValueError('Term precision and value disagree')
        return self


class ContractTermSource(Exact):
    term: TermName
    artifact_id: UUID
    artifact_version: int = Field(strict=True, ge=1, le=2147483647)
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    locator: str = Field(strict=True, min_length=1, max_length=1000)

    @field_validator('locator')
    @classmethod
    def actual_locator(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Use a page or clause reference')
        return value


class ContractTermsDraft(Exact):
    # Fields are required, even when unknown: clients must not silently omit money.
    purchase_price_cents: int | None = Field(strict=True, ge=1, le=MAX_CENTS)
    earnest_money_cents: int | None = Field(strict=True, ge=0, le=MAX_CENTS)
    assignment_allowed: StrictBool | None
    assignment_provisions: str | None = Field(strict=True, min_length=1, max_length=4000)
    effective: ContractDateTerm
    inspection_deadline: ContractDateTerm
    closing_deadline: ContractDateTerm
    sources: tuple[ContractTermSource, ...] = Field(max_length=6)
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('assignment_provisions', 'note')
    @classmethod
    def readable_text(cls, value):
        if value is not None and (not value.strip() or '\x00' in value):
            raise ValueError('Plain nonblank source text required')
        return value

    @model_validator(mode='after')
    def known_values_need_sources(self):
        names = [source.term for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError('One explicit source per term required')
        known = {'purchase_price': self.purchase_price_cents is not None,
                 'earnest_money': self.earnest_money_cents is not None,
                 'assignment': self.assignment_allowed is not None or self.assignment_provisions is not None,
                 'effective': self.effective.precision != 'unknown',
                 'inspection_deadline': self.inspection_deadline.precision != 'unknown',
                 'closing_deadline': self.closing_deadline.precision != 'unknown'}
        if any(present and name not in names for name, present in known.items()):
            raise ValueError('Every entered term must identify its source document and clause')
        if self.assignment_allowed is not None and self.assignment_provisions is None:
            raise ValueError('Assignment interpretation requires the source provision text')
        if len(self.note.strip()) < 20:
            raise ValueError('Describe the term preparation')
        return self


class ContractTermsRequest(Exact):
    id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)
    terms: ContractTermsDraft

    @model_validator(mode='after')
    def source_version_exists(self):
        if any(source.artifact_version > self.expected_version for source in self.terms.sources):
            raise ValueError('Source cannot belong to a future contract version')
        return self
