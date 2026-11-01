"""Explicit reviewer-supplied date interpretation; never a replacement contract term.

This isolated boundary is not an API or execution authorization. Persistence must
bind it to the current date-only term and independently verify the cited original.
"""
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, Field, field_validator, model_validator
from schemas.acquisition_contract_terms import Exact, ContractTermSource

DeadlineTerm = Literal['effective', 'inspection_deadline', 'closing_deadline']


class ContractDeadlineResolution(Exact):
    term: DeadlineTerm
    calendar_date: date
    local_time: str = Field(strict=True, pattern=r'^\d{2}:\d{2}:\d{2}$')
    time_zone: str = Field(strict=True, min_length=1, max_length=100)
    resolved_instant: AwareDatetime
    basis: Literal['explicit_document_time', 'reviewed_interpretation']
    source: ContractTermSource
    rationale: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('calendar_date', mode='before')
    @classmethod
    def explicit_calendar_date(cls, value):
        if type(value) is date:
            return value
        if isinstance(value, str) and len(value) == 10 and date.fromisoformat(value).isoformat() == value:
            return value
        raise ValueError('Preserve the original calendar date')

    @field_validator('resolved_instant', mode='before')
    @classmethod
    def explicit_offset(cls, value):
        if isinstance(value, datetime) or isinstance(value, str) and 'T' in value:
            return value
        raise ValueError('Explicit resolved instant and UTC offset required')

    @model_validator(mode='after')
    def coherent_source_and_local_time(self):
        if self.source.term != self.term:
            raise ValueError('The cited source must address this exact term')
        if len(self.rationale.strip()) < 20 or '\x00' in self.rationale:
            raise ValueError('Document the interpretation without inferring authority')
        try:
            zone = ZoneInfo(self.time_zone)
            wall_time = time.fromisoformat(self.local_time)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError('Use a named time zone and valid local time') from error
        local = self.resolved_instant.astimezone(zone)
        # An explicit offset disambiguates repeated DST times. Nonexistent local
        # times and offsets inconsistent with the named zone are rejected.
        if (local.date() != self.calendar_date or local.time() != wall_time
                or local.utcoffset() != self.resolved_instant.utcoffset()):
            raise ValueError('Date, local time, named zone and explicit offset must agree')
        return self


class ContractDeadlineResolutionRequest(Exact):
    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    resolution: ContractDeadlineResolution

    @model_validator(mode='after')
    def retained_source(self):
        if self.resolution.source.artifact_version > self.expected_version:
            raise ValueError('A future contract document cannot establish this deadline')
        return self
