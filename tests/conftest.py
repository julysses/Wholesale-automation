"""Shared pytest fixtures."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=False)
def mock_anthropic():
    """Patch Anthropic client globally for tests that don't need real API calls."""
    with patch("agents.base_agent.anthropic.Anthropic") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client
