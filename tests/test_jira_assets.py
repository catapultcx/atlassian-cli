"""Tests for atlassian_cli.jira_assets."""

import json
from argparse import Namespace

import pytest
import responses

from atlassian_cli.jira_assets import (
    _parse_attrs,
    cmd_attrs,
    cmd_create,
    cmd_delete,
    cmd_get,
    cmd_schema,
    cmd_schemas,
    cmd_search,
    cmd_type,
    cmd_type_create,
    cmd_types,
    cmd_update,
)
from atlassian_cli.output import set_json_mode

ASSETS_BASE = "https://api.atlassian.com/jsm/assets/workspace/ws-123/v1"


@pytest.fixture(autouse=True)
def _patch_setup(monkeypatch, mock_session):
    monkeypatch.setattr(
        "atlassian_cli.jira_assets.assets_setup",
        lambda: (mock_session, "https://test.atlassian.net", ASSETS_BASE),
    )
    set_json_mode(False)


class TestParseAttrs:
    def test_parses_key_value(self):
        result = _parse_attrs(["1=Server01", "2=10.0.0.1"])
        assert len(result) == 2
        assert result[0]["objectTypeAttributeId"] == "1"
        assert result[0]["objectAttributeValues"] == [{"value": "Server01"}]

    def test_handles_equals_in_value(self):
        result = _parse_attrs(["1=a=b"])
        assert result[0]["objectAttributeValues"] == [{"value": "a=b"}]

    def test_exits_on_invalid(self):
        with pytest.raises(SystemExit):
            _parse_attrs(["no-equals-sign"])


class TestCmdSearch:
    @responses.activate
    def test_search_objects(self, capsys):
        responses.add(
            responses.POST, f"{ASSETS_BASE}/object/aql",
            json={"values": [
                {"id": "1", "objectType": {"name": "Server"}, "label": "srv01"},
                {"id": "2", "objectType": {"name": "Server"}, "label": "srv02"},
            ]},
        )
        cmd_search(Namespace(aql="objectType=Server", max=50))
        out = capsys.readouterr().out
        assert "srv01" in out
        assert "2 objects found" in out


class TestCmdGet:
    @responses.activate
    def test_get_object(self, capsys):
        responses.add(
            responses.GET, f"{ASSETS_BASE}/object/42",
            json={"id": "42", "label": "MyServer", "objectType": {"name": "Server"}},
        )
        cmd_get(Namespace(id="42"))
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "42"


class TestCmdCreate:
    @responses.activate
    def test_create_object(self, capsys):
        responses.add(
            responses.POST, f"{ASSETS_BASE}/object/create",
            json={"id": "99", "label": "NewServer"},
        )
        cmd_create(Namespace(type_id="5", attrs=["1=NewServer", "2=10.0.0.1"]))
        out = capsys.readouterr().out
        assert "99" in out

    @responses.activate
    def test_create_sends_correct_body(self):
        responses.add(
            responses.POST, f"{ASSETS_BASE}/object/create",
            json={"id": "99", "label": "x"},
        )
        cmd_create(Namespace(type_id="5", attrs=["1=Name"]))
        body = json.loads(responses.calls[0].request.body)
        assert body["objectTypeId"] == "5"
        assert body["attributes"][0]["objectTypeAttributeId"] == "1"


class TestCmdUpdate:
    @responses.activate
    def test_update_object(self, capsys):
        responses.add(
            responses.PUT, f"{ASSETS_BASE}/object/42",
            json={"id": "42", "label": "Updated"},
        )
        cmd_update(Namespace(id="42", attrs=["1=Updated"]))
        assert "Updated object 42" in capsys.readouterr().out


class TestCmdDelete:
    @responses.activate
    def test_delete_object(self, capsys):
        responses.add(responses.DELETE, f"{ASSETS_BASE}/object/42", status=204)
        cmd_delete(Namespace(id="42"))
        assert "Deleted object 42" in capsys.readouterr().out


class TestCmdSchemas:
    @responses.activate
    def test_list_schemas(self, capsys):
        responses.add(
            responses.GET, f"{ASSETS_BASE}/objectschema/list",
            json={"values": [
                {"id": "1", "name": "IT Assets"},
                {"id": "2", "name": "HR Assets"},
            ]},
        )
        cmd_schemas(Namespace())
        out = capsys.readouterr().out
        assert "IT Assets" in out
        assert "2 schemas" in out


class TestCmdSchema:
    @responses.activate
    def test_get_schema(self, capsys):
        responses.add(
            responses.GET, f"{ASSETS_BASE}/objectschema/1",
            json={"id": "1", "name": "IT Assets", "objectCount": 150},
        )
        cmd_schema(Namespace(id="1"))
        out = json.loads(capsys.readouterr().out)
        assert out["name"] == "IT Assets"


class TestCmdTypes:
    @responses.activate
    def test_list_types(self, capsys):
        responses.add(
            responses.GET, f"{ASSETS_BASE}/objectschema/1/objecttypes/flat",
            json=[
                {"id": "5", "name": "Server"},
                {"id": "6", "name": "Network Device"},
            ],
        )
        cmd_types(Namespace(schema_id="1"))
        out = capsys.readouterr().out
        assert "Server" in out
        assert "2 types" in out


class TestCmdType:
    @responses.activate
    def test_get_type(self, capsys):
        responses.add(
            responses.GET, f"{ASSETS_BASE}/objecttype/5",
            json={"id": "5", "name": "Server", "objectCount": 42},
        )
        cmd_type(Namespace(id="5"))
        out = json.loads(capsys.readouterr().out)
        assert out["name"] == "Server"


class TestCmdTypeCreate:
    @responses.activate
    def test_create_type(self, capsys):
        responses.add(
            responses.POST, f"{ASSETS_BASE}/objecttype/create",
            json={"id": "10", "name": "Laptop"},
        )
        cmd_type_create(Namespace(schema_id="1", name="Laptop", description=None, parent_type_id=None))
        assert "Laptop" in capsys.readouterr().out

    @responses.activate
    def test_create_type_with_options(self, capsys):
        responses.add(
            responses.POST, f"{ASSETS_BASE}/objecttype/create",
            json={"id": "11", "name": "Desktop"},
        )
        cmd_type_create(Namespace(
            schema_id="1", name="Desktop",
            description="Desktop computers", parent_type_id="5",
        ))
        body = json.loads(responses.calls[0].request.body)
        assert body["description"] == "Desktop computers"
        assert body["parentObjectTypeId"] == "5"


class TestCmdAttrs:
    @responses.activate
    def test_list_attrs(self, capsys):
        responses.add(
            responses.GET, f"{ASSETS_BASE}/objecttype/5/attributes",
            json=[
                {"id": "1", "name": "Name", "type": "Default", "minimumCardinality": 1},
                {"id": "2", "name": "IP Address", "type": "Default", "minimumCardinality": 0},
            ],
        )
        cmd_attrs(Namespace(type_id="5"))
        out = capsys.readouterr().out
        assert "Name" in out
        assert "*" in out  # required marker
        assert "2 attributes" in out
