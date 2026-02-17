"""Tests for atlassian_cli.conflu (Confluence CLI)."""

import json
import os
from argparse import Namespace

import pytest
import responses

from atlassian_cli.conflu import (
    _ver,
    _ver_ts,
    cmd_diff,
    cmd_get,
    cmd_index,
    cmd_search,
    get_page,
    get_space,
    list_pages,
    load_adf,
    load_meta,
    save_page,
)
from atlassian_cli.output import set_json_mode

BASE = "https://test.atlassian.net"
V2 = "/wiki/api/v2"

SAMPLE_PAGE = {
    "id": "12345",
    "title": "Test Page",
    "spaceId": "100",
    "parentId": "99",
    "version": {"number": 3, "createdAt": "2025-01-15T10:00:00Z"},
    "body": {
        "atlas_doc_format": {
            "value": {"type": "doc", "version": 1, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}
            ]},
        },
    },
}

SAMPLE_SPACE = {"id": "100", "key": "TEST", "name": "Test Space"}


@pytest.fixture(autouse=True)
def _reset():
    set_json_mode(False)
    from atlassian_cli.conflu import _space_cache
    _space_cache.clear()


@pytest.fixture(autouse=True)
def _patch_setup(monkeypatch, mock_session, base_url):
    monkeypatch.setattr(
        "atlassian_cli.conflu.setup",
        lambda: (mock_session, base_url),
    )


class TestHelpers:
    def test_ver_dict(self):
        assert _ver({"version": {"number": 5}}) == 5

    def test_ver_missing(self):
        assert _ver({}) == 0

    def test_ver_ts(self):
        assert _ver_ts({"version": {"createdAt": "2025-01-01"}}) == "2025-01-01"


class TestGetPage:
    @responses.activate
    def test_fetches_page(self, mock_session):
        page_data = {
            "id": "12345", "title": "Test",
            "body": {"atlas_doc_format": {"value": '{"type":"doc","version":1,"content":[]}'}},
        }
        responses.add(responses.GET, f"{BASE}{V2}/pages/12345", json=page_data)
        result = get_page(mock_session, BASE, "12345")
        assert result["id"] == "12345"
        # Value should be parsed from JSON string
        assert isinstance(result["body"]["atlas_doc_format"]["value"], dict)


class TestGetSpace:
    @responses.activate
    def test_by_key(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces",
            json={"results": [SAMPLE_SPACE]},
        )
        space = get_space(mock_session, BASE, key="TEST")
        assert space["key"] == "TEST"

    @responses.activate
    def test_caches_result(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces",
            json={"results": [SAMPLE_SPACE]},
        )
        get_space(mock_session, BASE, key="TEST")
        # Second call should use cache, no new request
        space = get_space(mock_session, BASE, key="TEST")
        assert space["key"] == "TEST"
        assert len(responses.calls) == 1


class TestListPages:
    @responses.activate
    def test_single_page_result(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/pages",
            json={"results": [{"id": "1"}, {"id": "2"}], "_links": {}},
        )
        pages = list_pages(mock_session, BASE, "100")
        assert len(pages) == 2

    @responses.activate
    def test_pagination(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/pages",
            json={
                "results": [{"id": "1"}],
                "_links": {"next": f"{V2}/spaces/100/pages?cursor=abc"},
            },
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/pages",
            json={"results": [{"id": "2"}], "_links": {}},
        )
        pages = list_pages(mock_session, BASE, "100")
        assert len(pages) == 2


class TestSavePage:
    def test_saves_files(self, tmp_path):
        adf_path, meta_path = save_page(SAMPLE_PAGE, "TEST", str(tmp_path))
        assert os.path.isfile(adf_path)
        assert os.path.isfile(meta_path)

        with open(adf_path) as f:
            adf = json.load(f)
        assert adf["type"] == "doc"

        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["id"] == "12345"
        assert meta["title"] == "Test Page"
        assert meta["version"] == 3


class TestLoadMeta:
    def test_loads_existing(self, tmp_path):
        save_page(SAMPLE_PAGE, "TEST", str(tmp_path))
        meta = load_meta("12345", str(tmp_path))
        assert meta["title"] == "Test Page"

    def test_returns_none_when_missing(self, tmp_path):
        assert load_meta("99999", str(tmp_path)) is None


class TestLoadAdf:
    def test_loads_existing(self, tmp_path):
        save_page(SAMPLE_PAGE, "TEST", str(tmp_path))
        adf = load_adf("12345", str(tmp_path))
        assert adf["type"] == "doc"

    def test_returns_none_when_missing(self, tmp_path):
        assert load_adf("99999", str(tmp_path)) is None


class TestCmdGet:
    @responses.activate
    def test_downloads_page(self, capsys, tmp_path):
        responses.add(responses.GET, f"{BASE}{V2}/pages/12345", json=SAMPLE_PAGE)
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100",
            json=SAMPLE_SPACE,
        )
        cmd_get(Namespace(page_id="12345", dir=str(tmp_path)))
        out = capsys.readouterr().out
        assert "Test Page" in out
        assert os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.json"))


class TestCmdDiff:
    @responses.activate
    def test_no_diff(self, capsys, tmp_path):
        save_page(SAMPLE_PAGE, "TEST", str(tmp_path))
        responses.add(responses.GET, f"{BASE}{V2}/pages/12345", json=SAMPLE_PAGE)
        cmd_diff(Namespace(page_id="12345", dir=str(tmp_path)))
        out = capsys.readouterr().out
        assert "No differences" in out

    def test_missing_local(self, tmp_path):
        with pytest.raises(SystemExit):
            cmd_diff(Namespace(page_id="99999", dir=str(tmp_path)))


class TestCmdSearch:
    def test_finds_by_title(self, capsys, tmp_path):
        index = {"TEST": [{"id": "1", "title": "Risk Policy", "spaceKey": "TEST"}]}
        index_path = str(tmp_path / "index.json")
        with open(index_path, "w") as f:
            json.dump(index, f)
        cmd_search(Namespace(query="risk", index=index_path))
        assert "Risk Policy" in capsys.readouterr().out

    def test_no_results(self, capsys, tmp_path):
        index_path = str(tmp_path / "index.json")
        with open(index_path, "w") as f:
            json.dump({"TEST": [{"id": "1", "title": "Something"}]}, f)
        cmd_search(Namespace(query="nonexistent", index=index_path))
        assert "No results" in capsys.readouterr().err

    def test_missing_index(self):
        with pytest.raises(SystemExit):
            cmd_search(Namespace(query="test", index="/nonexistent/index.json"))


class TestCmdIndex:
    @responses.activate
    def test_indexes_spaces(self, capsys, tmp_path):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces",
            json={"results": [SAMPLE_SPACE]},
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/pages",
            json={"results": [
                {"id": "1", "title": "Page 1", "parentId": "", "version": {"number": 1, "createdAt": "2025-01-01"}},
            ], "_links": {}},
        )
        output_path = str(tmp_path / "index.json")
        cmd_index(Namespace(space=["TEST"], output=output_path))
        out = capsys.readouterr().out
        assert "1 pages indexed" in out
        with open(output_path) as f:
            index = json.load(f)
        assert len(index["TEST"]) == 1
