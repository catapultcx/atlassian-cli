"""Shared test fixtures."""

import pytest
import responses
from requests import Session
from requests.auth import HTTPBasicAuth


@pytest.fixture
def mock_session():
    """Authenticated requests.Session for testing."""
    s = Session()
    s.auth = HTTPBasicAuth("test@example.com", "fake-token")
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return s


@pytest.fixture
def base_url():
    return "https://test.atlassian.net"


@pytest.fixture
def mocked_responses():
    """Activate responses mock for the duration of a test."""
    with responses.RequestsMock() as rsps:
        yield rsps
