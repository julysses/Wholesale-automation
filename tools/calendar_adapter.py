"""
Calendar Adapter — sync deal milestones to Google Calendar or Calendly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from config.settings import settings

logger = logging.getLogger(__name__)


class CalendarAdapter:
    """
    Adapter for syncing deal milestones (inspections, closings) to a calendar.
    """

    def __init__(self) -> None:
        self._google_calendar_id = settings.google_calendar_id
        self._calendly_api_key = settings.calendly_api_key
        # If no credentials, default to dry-run
        self._dry_run = not (self._google_calendar_id or self._calendly_api_key)

    def sync_deal_milestones(
        self,
        deal_id: str,
        address: str,
        milestones: dict[str, datetime],
    ) -> bool:
        """
        Sync deal milestones to the configured calendar.
        milestones example: {"Inspection": dt, "Closing": dt}
        """
        if self._dry_run:
            for name, dt in milestones.items():
                logger.info(
                    f"[Calendar][DRY-RUN] Syncing {name} for {address} "
                    f"to {dt.strftime('%Y-%m-%d %H:%M')}"
                )
            return True

        success = True
        if self._google_calendar_id:
            success &= self._sync_google_calendar(address, milestones)
        
        if self._calendly_api_key:
            # Note: Calendly is usually inbound (seller books via link), 
            # but we can create one-off meetings via API if needed.
            success &= self._sync_calendly(address, milestones)
            
        return success

    def _sync_google_calendar(self, address: str, milestones: dict[str, datetime]) -> bool:
        """Placeholder for Google Calendar API integration via httpx."""
        for name, dt in milestones.items():
            logger.info(f"[Calendar][Google] Syncing {name} for {address} to {self._google_calendar_id}")
            # Implementation would go here (OAuth2 token handling + POST /calendars/{id}/events)
        return True

    def _sync_calendly(self, address: str, milestones: dict[str, datetime]) -> bool:
        """Placeholder for Calendly API integration via httpx."""
        for name, dt in milestones.items():
            logger.info(f"[Calendar][Calendly] Creating meeting for {address} using API key {self._calendly_api_key[:4]}...")
        return True
