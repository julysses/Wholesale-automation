"""Trusted database proof projection; public input contains only a lead identifier."""
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from schemas.acquisition_mail_preparation import ExactModel, ContentReviewState


class MailProofRequest(ExactModel):
    lead_id: UUID


class MailProofProperty(ExactModel):
    property_id: UUID
    lead_id: UUID
    address_std: str = Field(min_length=1, max_length=500)
    unit: str | None = Field(max_length=100)
    city: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    zip: str | None = Field(max_length=30)


class MailProofContext(ExactModel):
    workspace_id: UUID
    campaign_id: UUID
    content_id: UUID
    lead_id: UUID
    property: MailProofProperty
    review_state: ContentReviewState
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def check_sources(self):
        review = self.review_state
        if (self.execution_authorized or self.property.lead_id != self.lead_id
                or (review.workspace_id, review.campaign_id, review.content_id) != (self.workspace_id, self.campaign_id, self.content_id)
                or review.checked_at != self.checked_at):
            raise ValueError('Proof sources do not share the requested snapshot')
        return self
