"""Tests for atlassian_cli.http."""

import pytest
import responses

from atlassian_cli.http import APIError, api_delete, api_get, api_post, api_put

BASE = "https://test.atlassian.net"


class TestAPIError:
    def test_str_truncates(self):
        e = APIError(400, "x" * 300)
        assert str(e).startswith("HTTP 400: ")
        assert len(str(e)) <= 215

    def test_status_and_body(self):
        e = APIError(404, "Not found")
        assert e.status == 404
        assert e.body == "Not found"


class TestApiGet:
    @responses.activate
    def test_success(self, mock_session):
        responses.add(responses.GET, f"{BASE}/test", json={"ok": True})
        result = api_get(mock_session, BASE, "/test")
        assert result == {"ok": True}

    @responses.activate
    def test_with_params(self, mock_session):
        responses.add(responses.GET, f"{BASE}/test", json={"ok": True})
        api_get(mock_session, BASE, "/test", foo="bar")
        assert "foo=bar" in responses.calls[0].request.url

    @responses.activate
    def test_raises_on_error(self, mock_session):
        responses.add(responses.GET, f"{BASE}/test", status=404, body="Not found")
        with pytest.raises(APIError) as exc_info:
            api_get(mock_session, BASE, "/test")
        assert exc_info.value.status == 404


class TestApiPost:
    @responses.activate
    def test_success(self, mock_session):
        responses.add(responses.POST, f"{BASE}/test", json={"id": "123"})
        result = api_post(mock_session, BASE, "/test", {"name": "test"})
        assert result == {"id": "123"}

    @responses.activate
    def test_raises_on_error(self, mock_session):
        responses.add(responses.POST, f"{BASE}/test", status=400, body="Bad request")
        with pytest.raises(APIError) as exc_info:
            api_post(mock_session, BASE, "/test", {})
        assert exc_info.value.status == 400


class TestApiPut:
    @responses.activate
    def test_success(self, mock_session):
        responses.add(responses.PUT, f"{BASE}/test", json={"updated": True})
        result = api_put(mock_session, BASE, "/test", {"name": "new"})
        assert result == {"updated": True}

    @responses.activate
    def test_raises_on_error(self, mock_session):
        responses.add(responses.PUT, f"{BASE}/test", status=403, body="Forbidden")
        with pytest.raises(APIError):
            api_put(mock_session, BASE, "/test", {})


class TestApiDelete:
    @responses.activate
    def test_204_returns_none(self, mock_session):
        responses.add(responses.DELETE, f"{BASE}/test", status=204)
        result = api_delete(mock_session, BASE, "/test")
        assert result is None

    @responses.activate
    def test_200_returns_json(self, mock_session):
        responses.add(responses.DELETE, f"{BASE}/test", json={"deleted": True})
        result = api_delete(mock_session, BASE, "/test")
        assert result == {"deleted": True}

    @responses.activate
    def test_raises_on_error(self, mock_session):
        responses.add(responses.DELETE, f"{BASE}/test", status=404, body="Not found")
        with pytest.raises(APIError):
            api_delete(mock_session, BASE, "/test")
