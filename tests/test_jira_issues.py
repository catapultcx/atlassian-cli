"""Tests for atlassian_cli.jira_issues."""

import json
from argparse import Namespace

import pytest
import responses

from atlassian_cli.jira_issues import (
    _extract_text,
    _text_adf,
    cmd_comment,
    cmd_comments,
    cmd_create,
    cmd_delete,
    cmd_get,
    cmd_search,
    cmd_transition,
    cmd_update,
)
from atlassian_cli.output import set_json_mode

BASE = "https://test.atlassian.net"
V3 = "/rest/api/3"


@pytest.fixture(autouse=True)
def _patch_setup(monkeypatch, mock_session, base_url):
    monkeypatch.setattr(
        "atlassian_cli.jira_issues.setup",
        lambda: (mock_session, base_url),
    )
    set_json_mode(False)


class TestTextAdf:
    def test_wraps_text(self):
        result = _text_adf("Hello world")
        assert result["type"] == "doc"
        assert result["content"][0]["content"][0]["text"] == "Hello world"

    def test_extracts_text(self):
        adf = _text_adf("Hello world")
        assert _extract_text(adf) == "Hello world"

    def test_extracts_nested(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ]},
            ],
        }
        assert _extract_text(adf) == "Hello  world"


class TestCmdGet:
    @responses.activate
    def test_get_issue(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V3}/issue/PROJ-1",
            json={
                "key": "PROJ-1", "id": "10001",
                "fields": {"summary": "Test issue", "status": {"name": "Open"}},
            },
        )
        cmd_get(Namespace(key="PROJ-1"))
        out = capsys.readouterr().out
        assert "PROJ-1" in out
        assert "Open" in out
        assert "Test issue" in out


class TestCmdCreate:
    @responses.activate
    def test_create_minimal(self, capsys):
        responses.add(
            responses.POST, f"{BASE}{V3}/issue",
            json={"key": "PROJ-2", "id": "10002"},
        )
        cmd_create(Namespace(
            project="PROJ", type="Task", summary="New task",
            description=None, labels=None, assignee=None, parent=None,
        ))
        out = capsys.readouterr().out
        assert "PROJ-2" in out

    @responses.activate
    def test_create_with_all_fields(self, capsys):
        responses.add(
            responses.POST, f"{BASE}{V3}/issue",
            json={"key": "PROJ-3", "id": "10003"},
        )
        cmd_create(Namespace(
            project="PROJ", type="Bug", summary="A bug",
            description="Details here", labels=["bug", "urgent"],
            assignee="abc123", parent="PROJ-1",
        ))
        body = json.loads(responses.calls[0].request.body)
        assert body["fields"]["labels"] == ["bug", "urgent"]
        assert body["fields"]["assignee"]["accountId"] == "abc123"
        assert body["fields"]["parent"]["key"] == "PROJ-1"
        assert body["fields"]["description"]["type"] == "doc"


class TestCmdUpdate:
    @responses.activate
    def test_update_summary(self, capsys):
        responses.add(responses.PUT, f"{BASE}{V3}/issue/PROJ-1", status=204)
        cmd_update(Namespace(
            key="PROJ-1", summary="Updated", description=None,
            labels=None, assignee=None, fields=None,
            add_labels=None, remove_labels=None,
        ))
        out = capsys.readouterr().out
        assert "Updated PROJ-1" in out

    def test_update_no_fields_exits(self, capsys):
        with pytest.raises(SystemExit):
            cmd_update(Namespace(
                key="PROJ-1", summary=None, description=None,
                labels=None, assignee=None, fields=None,
                add_labels=None, remove_labels=None,
            ))

    @responses.activate
    def test_update_with_custom_fields(self, capsys):
        responses.add(responses.PUT, f"{BASE}{V3}/issue/PROJ-1", status=204)
        cmd_update(Namespace(
            key="PROJ-1", summary=None, description=None,
            labels=None, assignee=None, fields='{"priority": {"name": "High"}}',
            add_labels=None, remove_labels=None,
        ))
        body = json.loads(responses.calls[0].request.body)
        assert body["fields"]["priority"]["name"] == "High"


class TestCmdDelete:
    @responses.activate
    def test_delete(self, capsys):
        responses.add(responses.DELETE, f"{BASE}{V3}/issue/PROJ-1", status=204)
        cmd_delete(Namespace(key="PROJ-1"))
        assert "Deleted PROJ-1" in capsys.readouterr().out


class TestCmdSearch:
    @responses.activate
    def test_search(self, capsys):
        responses.add(
            responses.POST, f"{BASE}{V3}/search/jql",
            json={"issues": [
                {"key": "PROJ-1", "fields": {"summary": "Issue 1", "status": {"name": "Open"}}},
                {"key": "PROJ-2", "fields": {"summary": "Issue 2", "status": {"name": "Done"}}},
            ]},
        )
        cmd_search(Namespace(jql="project=PROJ", max=50, fields="summary,status", all=False, dump=None))
        out = capsys.readouterr().out
        assert "PROJ-1" in out
        assert "PROJ-2" in out
        assert "2 issues found" in out


class TestCmdTransition:
    @responses.activate
    def test_transition_by_name(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V3}/issue/PROJ-1/transitions",
            json={"transitions": [
                {"id": "31", "name": "Done", "to": {"name": "Done"}},
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            ]},
        )
        responses.add(responses.POST, f"{BASE}{V3}/issue/PROJ-1/transitions", json={})
        cmd_transition(Namespace(key="PROJ-1", status="Done"))
        out = capsys.readouterr().out
        assert "Done" in out

    @responses.activate
    def test_transition_not_found(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V3}/issue/PROJ-1/transitions",
            json={"transitions": [
                {"id": "31", "name": "Done", "to": {"name": "Done"}},
            ]},
        )
        with pytest.raises(SystemExit):
            cmd_transition(Namespace(key="PROJ-1", status="Nonexistent"))


class TestCmdComment:
    @responses.activate
    def test_add_comment(self, capsys):
        responses.add(responses.POST, f"{BASE}{V3}/issue/PROJ-1/comment", json={"id": "1"})
        cmd_comment(Namespace(key="PROJ-1", body="A comment"))
        assert "Comment added" in capsys.readouterr().out

    @responses.activate
    def test_comment_sends_adf(self):
        responses.add(responses.POST, f"{BASE}{V3}/issue/PROJ-1/comment", json={"id": "1"})
        cmd_comment(Namespace(key="PROJ-1", body="Hello"))
        body = json.loads(responses.calls[0].request.body)
        assert body["body"]["type"] == "doc"


class TestCmdComments:
    @responses.activate
    def test_list_comments(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V3}/issue/PROJ-1/comment",
            json={"comments": [
                {
                    "author": {"displayName": "Alice"},
                    "created": "2025-01-15T10:00:00",
                    "body": _text_adf("First comment"),
                },
                {
                    "author": {"displayName": "Bob"},
                    "created": "2025-01-16T12:00:00",
                    "body": _text_adf("Second comment"),
                },
            ]},
        )
        cmd_comments(Namespace(key="PROJ-1"))
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "2 comments" in out
