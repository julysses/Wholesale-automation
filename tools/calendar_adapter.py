"""Calendar capability reporting until an authenticated provider integration is installed."""
from __future__ import annotations

import logging
from datetime import datetime
from config.settings import settings

logger = logging.getLogger(__name__)


class CalendarAdapter:
    def __init__(self) -> None:
        self.status = "not_supported" if (settings.google_calendar_id or settings.calendly_api_key) else "not_configured"

    def sync_deal_milestones(self, deal_id: str, address: str, milestones: dict[str, datetime]) -> bool:
        """Return false: saving a milestone does not create an external calendar event."""
        logger.warning("External calendar sync unavailable (%s); milestone remains in the app", self.status)
        return False
