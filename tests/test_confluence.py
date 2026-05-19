"""Tests for atlassian_cli.confluence (Confluence CLI)."""

import json
import os
from argparse import Namespace

import pytest
import responses

from atlassian_cli.confluence import (
    _adf_to_text,
    _make_adf_body,
    _ver,
    _ver_ts,
    cmd_blog_create,
    cmd_blog_delete,
    cmd_blog_get,
    cmd_blog_list,
    cmd_blog_update,
    cmd_cql,
    cmd_diff,
    cmd_get,
    cmd_index,
    cmd_search,
    cmd_sync,
    create_blogpost,
    get_blogpost,
    get_page,
    get_space,
    list_blogposts,
    list_comment_replies,
    list_comments,
    list_pages,
    load_adf,
    load_meta,
    reply_to_comment,
    resolve_comment,
    save_page,
    update_blogpost,
)
from atlassian_cli.output import set_json_mode

BASE = "https://test.atlassian.net"
V1 = "/wiki/rest/api"
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
    from atlassian_cli.confluence import _space_cache
    _space_cache.clear()


@pytest.fixture(autouse=True)
def _patch_setup(monkeypatch, mock_session, base_url):
    monkeypatch.setattr(
        "atlassian_cli.confluence.setup",
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

    def test_md_format_writes_md_only(self, tmp_path):
        body_path, meta_path = save_page(SAMPLE_PAGE, "TEST", str(tmp_path), output_format="md")
        assert body_path.endswith(".md")
        assert os.path.isfile(body_path)
        assert os.path.isfile(meta_path)

        with open(body_path) as f:
            md = f.read()
        assert "Hello" in md

        # No ADF JSON file when --md
        assert not os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.json"))


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
        cmd_get(Namespace(page_id="12345", dir=str(tmp_path), md=False))
        out = capsys.readouterr().out
        assert "Test Page" in out
        assert os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.json"))

    @responses.activate
    def test_downloads_page_as_md(self, capsys, tmp_path):
        responses.add(responses.GET, f"{BASE}{V2}/pages/12345", json=SAMPLE_PAGE)
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100",
            json=SAMPLE_SPACE,
        )
        cmd_get(Namespace(page_id="12345", dir=str(tmp_path), md=True))
        assert os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.md"))
        assert not os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.json"))


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


class TestAdfToText:
    def test_simple_text(self):
        node = {"type": "text", "text": "Hello"}
        assert _adf_to_text(node) == "Hello"

    def test_paragraph(self):
        node = {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}
        assert _adf_to_text(node) == "Hello world"

    def test_nested(self):
        node = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
        ]}
        assert _adf_to_text(node) == "FirstSecond"

    def test_json_string(self):
        s = '{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"From string"}]}]}'
        assert _adf_to_text(s) == "From string"

    def test_hard_break(self):
        node = {"type": "paragraph", "content": [
            {"type": "text", "text": "Line 1"},
            {"type": "hardBreak"},
            {"type": "text", "text": "Line 2"},
        ]}
        assert _adf_to_text(node) == "Line 1\nLine 2"


class TestMakeAdfBody:
    def test_creates_doc(self):
        result = _make_adf_body("Hello")
        assert result["type"] == "doc"
        assert result["content"][0]["content"][0]["text"] == "Hello"

    def test_markdown_heading_and_list(self):
        md = "# Title\n\n- item one\n- item two"
        result = _make_adf_body(md)
        types = [n["type"] for n in result["content"]]
        assert types == ["heading", "bulletList"]
        assert result["content"][0]["attrs"]["level"] == 1
        items = result["content"][1]["content"]
        assert len(items) == 2

    def test_empty_text(self):
        result = _make_adf_body("")
        assert result["type"] == "doc"
        assert len(result["content"]) >= 1


class TestListComments:
    @responses.activate
    def test_fetches_inline_comments(self, mock_session):
        responses.add(
            responses.GET,
            f"{BASE}{V2}/pages/123/inline-comments",
            json={"results": [
                {"id": "c1", "status": "current", "resolutionStatus": "open",
                 "version": {"authorId": "user1", "createdAt": "2025-01-01"},
                 "body": {"atlas_doc_format": {"value": '{"type":"doc","content":[]}'}},
                 "properties": {}},
            ], "_links": {}},
        )
        comments = list_comments(mock_session, BASE, "123", "inline")
        assert len(comments) == 1
        assert comments[0]["id"] == "c1"

    @responses.activate
    def test_fetches_footer_comments(self, mock_session):
        responses.add(
            responses.GET,
            f"{BASE}{V2}/pages/123/footer-comments",
            json={"results": [], "_links": {}},
        )
        comments = list_comments(mock_session, BASE, "123", "footer")
        assert len(comments) == 0


class TestListCommentReplies:
    @responses.activate
    def test_fetches_replies(self, mock_session):
        responses.add(
            responses.GET,
            f"{BASE}{V2}/inline-comments/c1/children",
            json={"results": [
                {"id": "r1", "version": {"authorId": "user2", "createdAt": "2025-01-02"},
                 "body": {"atlas_doc_format": {"value": '{"type":"doc","content":[]}'}}},
            ], "_links": {}},
        )
        replies = list_comment_replies(mock_session, BASE, "c1", "inline")
        assert len(replies) == 1
        assert replies[0]["id"] == "r1"

    @responses.activate
    def test_returns_empty_on_404(self, mock_session):
        responses.add(
            responses.GET,
            f"{BASE}{V2}/inline-comments/c1/children",
            status=404,
        )
        replies = list_comment_replies(mock_session, BASE, "c1", "inline")
        assert replies == []


class TestReplyToComment:
    @responses.activate
    def test_posts_reply(self, mock_session):
        responses.add(
            responses.POST,
            f"{BASE}{V2}/inline-comments",
            json={"id": "new-reply", "status": "current"},
        )
        result = reply_to_comment(mock_session, BASE, "c1", "My reply", "inline")
        assert result["id"] == "new-reply"
        body = json.loads(responses.calls[0].request.body)
        assert body["parentCommentId"] == "c1"


class TestResolveComment:
    @responses.activate
    def test_resolves(self, mock_session):
        responses.add(
            responses.GET,
            f"{BASE}{V2}/inline-comments/c1",
            json={"id": "c1", "version": {"number": 2},
                  "body": {"atlas_doc_format": {"value": '{"type":"doc","content":[]}'}}},
        )
        responses.add(
            responses.PUT,
            f"{BASE}{V2}/inline-comments/c1",
            json={"id": "c1", "resolutionStatus": "resolved", "version": {"number": 3}},
        )
        result = resolve_comment(mock_session, BASE, "c1", resolved=True)
        assert result["resolutionStatus"] == "resolved"
        body = json.loads(responses.calls[1].request.body)
        assert body["resolved"] is True
        assert body["version"]["number"] == 3

    @responses.activate
    def test_reopens(self, mock_session):
        responses.add(
            responses.GET,
            f"{BASE}{V2}/inline-comments/c1",
            json={"id": "c1", "version": {"number": 3},
                  "body": {"atlas_doc_format": {"value": '{"type":"doc","content":[]}'}}},
        )
        responses.add(
            responses.PUT,
            f"{BASE}{V2}/inline-comments/c1",
            json={"id": "c1", "resolutionStatus": "reopened", "version": {"number": 4}},
        )
        resolve_comment(mock_session, BASE, "c1", resolved=False)
        body = json.loads(responses.calls[1].request.body)
        assert body["resolved"] is False


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


# ---------------------------------------------------------------------------
# Blog post tests
# ---------------------------------------------------------------------------

BLOG_SAMPLE = {
    "id": "55555",
    "title": "Test Blog Post",
    "spaceId": "100",
    "status": "current",
    "version": {"number": 1, "createdAt": "2025-02-01T10:00:00Z"},
    "body": {
        "atlas_doc_format": {
            "value": {"type": "doc", "version": 1, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Blog content"}]}
            ]},
        },
    },
}


class TestCreateBlogpost:
    @responses.activate
    def test_creates_blogpost(self, mock_session):
        responses.add(
            responses.POST, f"{BASE}{V2}/blogposts",
            json=BLOG_SAMPLE,
        )
        result = create_blogpost(mock_session, BASE, "100", "Test Blog Post",
                                 body="Blog content")
        assert result["id"] == "55555"
        assert result["title"] == "Test Blog Post"

    @responses.activate
    def test_creates_with_file(self, mock_session, tmp_path):
        adf_file = tmp_path / "blog.adf.json"
        adf_file.write_text(json.dumps(BLOG_SAMPLE["body"]["atlas_doc_format"]["value"]))
        responses.add(
            responses.POST, f"{BASE}{V2}/blogposts",
            json=BLOG_SAMPLE,
        )
        result = create_blogpost(mock_session, BASE, "100", "Test Blog Post",
                                 file=str(adf_file))
        assert result["id"] == "55555"


class TestGetBlogpost:
    @responses.activate
    def test_fetches_blogpost(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/blogposts/55555",
            json=BLOG_SAMPLE,
        )
        result = get_blogpost(mock_session, BASE, "55555")
        assert result["id"] == "55555"
        assert isinstance(result["body"]["atlas_doc_format"]["value"], dict)


class TestListBlogposts:
    @responses.activate
    def test_lists_blogposts(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/blogposts",
            json={"results": [BLOG_SAMPLE], "_links": {}},
        )
        result = list_blogposts(mock_session, BASE, "100")
        assert len(result) == 1
        assert result[0]["id"] == "55555"


class TestCmdBlogCreate:
    @responses.activate
    def test_creates_blogpost(self, capsys, tmp_path):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces",
            json={"results": [SAMPLE_SPACE]},
        )
        responses.add(
            responses.POST, f"{BASE}{V2}/blogposts",
            json=BLOG_SAMPLE,
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/blogposts/55555",
            json=BLOG_SAMPLE,
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100",
            json=SAMPLE_SPACE,
        )
        cmd_blog_create(Namespace(
            space_key="TEST", title="Test Blog Post",
            body="Blog content", file=None,
            dir=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert "Test Blog Post" in out
        assert os.path.isfile(os.path.join(str(tmp_path), "TEST", "blog-55555.json"))


class TestCmdBlogGet:
    @responses.activate
    def test_downloads_blogpost(self, capsys, tmp_path):
        responses.add(
            responses.GET, f"{BASE}{V2}/blogposts/55555",
            json=BLOG_SAMPLE,
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100",
            json=SAMPLE_SPACE,
        )
        cmd_blog_get(Namespace(blogpost_id="55555", dir=str(tmp_path)))
        out = capsys.readouterr().out
        assert "Test Blog Post" in out
        assert os.path.isfile(os.path.join(str(tmp_path), "TEST", "blog-55555.json"))


class TestCmdBlogDelete:
    @responses.activate
    def test_deletes_blogpost(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V2}/blogposts/55555",
            json=BLOG_SAMPLE,
        )
        responses.add(
            responses.DELETE, f"{BASE}{V2}/blogposts/55555",
            status=204,
        )
        cmd_blog_delete(Namespace(blogpost_id="55555"))
        out = capsys.readouterr().out
        assert "Deleted blog post" in out


class TestCmdBlogList:
    @responses.activate
    def test_lists_blogposts(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces",
            json={"results": [SAMPLE_SPACE]},
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/blogposts",
            json={"results": [BLOG_SAMPLE], "_links": {}},
        )
        cmd_blog_list(Namespace(space_key="TEST"))
        out = capsys.readouterr().out
        assert "Test Blog Post" in out
        assert "1 blog post(s)" in out


class TestCmdBlogUpdate:
    @responses.activate
    def test_updates_blogpost(self, capsys, tmp_path):
        responses.add(
            responses.GET, f"{BASE}{V2}/blogposts/55555",
            json=BLOG_SAMPLE,
        )
        responses.add(
            responses.PUT, f"{BASE}{V2}/blogposts/55555",
            json={**BLOG_SAMPLE, "title": "Updated Title",
                  "version": {"number": 2, "createdAt": "2025-02-02T10:00:00Z"}},
        )
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100",
            json=SAMPLE_SPACE,
        )
        cmd_blog_update(Namespace(
            blogpost_id="55555", title="Updated Title",
            body=None, file=None,
            dir=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert "Updated Title" in out
        assert "(v2)" in out


class TestUpdateBlogpost:
    @responses.activate
    def test_updates_title_and_body(self, mock_session):
        responses.add(
            responses.GET, f"{BASE}{V2}/blogposts/55555",
            json=BLOG_SAMPLE,
        )
        responses.add(
            responses.PUT, f"{BASE}{V2}/blogposts/55555",
            json={**BLOG_SAMPLE, "title": "New Title",
                  "version": {"number": 2, "createdAt": "2025-02-02T10:00:00Z"}},
        )
        title, ver = update_blogpost(mock_session, BASE, "55555",
                                     title="New Title", body="New body")
        assert title == "New Title"
        assert ver == 2


class TestCmdSync:
    @responses.activate
    def test_renders_pages_as_md(self, capsys, tmp_path):
        # Space lookup
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces",
            json={"results": [SAMPLE_SPACE]},
        )
        # Page list
        responses.add(
            responses.GET, f"{BASE}{V2}/spaces/100/pages",
            json={"results": [{"id": "12345", "version": {"number": 3}}], "_links": {}},
        )
        # Page fetch
        responses.add(responses.GET, f"{BASE}{V2}/pages/12345", json=SAMPLE_PAGE)

        cmd_sync(Namespace(
            space_key="TEST",
            dir=str(tmp_path),
            workers=1,
            force=True,
            md=True,
        ))

        assert os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.md"))
        assert not os.path.isfile(os.path.join(str(tmp_path), "TEST", "12345.json"))


SAMPLE_CQL_RESPONSE = {
    "results": [
        {
            "content": {
                "id": "12345",
                "type": "page",
                "title": "Risk Policy",
                "space": {"key": "POL"},
            },
            "title": "Risk Policy",
            "url": "/spaces/POL/pages/12345",
            "excerpt": "Risks are managed via …",
        },
        {
            "content": {
                "id": "67890",
                "type": "page",
                "title": "Risk Register",
                "space": {"key": "COMPLY"},
            },
            "title": "Risk Register",
            "url": "/spaces/COMPLY/pages/67890",
            "excerpt": "Open risks: …",
        },
    ],
    "totalSize": 2,
}


class TestCmdCql:
    @responses.activate
    def test_text_output(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V1}/search",
            json=SAMPLE_CQL_RESPONSE,
        )
        cmd_cql(Namespace(query='text ~ "risk"', space=None, limit=25, md=False))
        out = capsys.readouterr().out
        assert "Risk Policy" in out
        assert "12345" in out
        assert "POL" in out

    @responses.activate
    def test_json_output(self, capsys):
        from atlassian_cli.output import set_json_mode
        responses.add(
            responses.GET, f"{BASE}{V1}/search",
            json=SAMPLE_CQL_RESPONSE,
        )
        set_json_mode(True)
        try:
            cmd_cql(Namespace(query='text ~ "risk"', space=None, limit=25, md=False))
        finally:
            set_json_mode(False)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert parsed[0]["id"] == "12345"
        assert parsed[0]["space"] == "POL"
        assert parsed[0]["title"] == "Risk Policy"

    @responses.activate
    def test_md_output(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V1}/search",
            json=SAMPLE_CQL_RESPONSE,
        )
        cmd_cql(Namespace(query='text ~ "risk"', space=None, limit=25, md=True))
        out = capsys.readouterr().out
        assert "Risk Policy" in out
        assert "- " in out
        assert "12345" in out

    @responses.activate
    def test_space_filter_prepends_clause(self):
        captured = {}

        def callback(request):
            captured["url"] = request.url
            return (200, {}, json.dumps(SAMPLE_CQL_RESPONSE))

        responses.add_callback(
            responses.GET, f"{BASE}{V1}/search", callback=callback,
        )
        cmd_cql(Namespace(query='text ~ "risk"', space="POL", limit=25, md=False))
        # The space clause should be present in the URL-encoded CQL
        assert 'space+%3D+%22POL%22' in captured["url"] or 'space%3D%22POL%22' in captured["url"]

    @responses.activate
    def test_no_results(self, capsys):
        responses.add(
            responses.GET, f"{BASE}{V1}/search",
            json={"results": [], "totalSize": 0},
        )
        cmd_cql(Namespace(query='text ~ "nothing"', space=None, limit=25, md=False))
        err = capsys.readouterr().err
        assert "No results" in err
