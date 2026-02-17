"""Tests for atlassian_cli.adf module."""

import pytest

from atlassian_cli.adf import (
    adf_to_markdown,
    bold,
    bullet_list,
    code_block,
    expand,
    extract_extension,
    extract_section,
    find_extensions,
    find_sections,
    heading,
    insert_after,
    md_to_adf,
    ordered_list,
    panel,
    para,
    replace_extension,
    replace_section,
    rule,
    status_badge,
    table,
    text,
)

# ---------------------------------------------------------------------------
# Fixtures — sample ADF documents
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_doc():
    """A multi-section ADF doc for testing section operations."""
    return [
        heading(1, "Title"),
        para("Intro paragraph."),
        heading(2, "Section A"),
        para("Content of section A."),
        para("More A content."),
        heading(2, "Section B"),
        para("Content of section B."),
        heading(3, "Section B.1"),
        para("Subsection of B."),
        heading(2, "Section C"),
        para("Content of section C."),
    ]


# ---------------------------------------------------------------------------
# adf_to_markdown
# ---------------------------------------------------------------------------

class TestAdfToMarkdown:
    def test_simple_doc(self):
        nodes = [heading(2, "Hello"), para("World")]
        md = adf_to_markdown(nodes)
        assert '## Hello' in md
        assert 'World' in md

    def test_full_doc_format(self):
        doc = {'type': 'doc', 'version': 1, 'content': [para("test")]}
        md = adf_to_markdown(doc)
        assert 'test' in md

    def test_bullet_list(self):
        nodes = [bullet_list(["one", "two", "three"])]
        md = adf_to_markdown(nodes)
        assert 'one' in md
        assert 'two' in md

    def test_table(self):
        nodes = [table(["A", "B"], [["1", "2"], ["3", "4"]])]
        md = adf_to_markdown(nodes)
        assert 'A' in md
        assert '1' in md


# ---------------------------------------------------------------------------
# find_sections
# ---------------------------------------------------------------------------

class TestFindSections:
    def test_finds_all_headings(self, sample_doc):
        sections = find_sections(sample_doc)
        headings = [s['heading'] for s in sections]
        assert headings == ['Title', 'Section A', 'Section B', 'Section B.1', 'Section C']

    def test_section_boundaries(self, sample_doc):
        sections = find_sections(sample_doc)
        by_name = {s['heading']: s for s in sections}

        # Title (h1) spans entire doc
        assert by_name['Title']['start'] == 0
        assert by_name['Title']['end'] == len(sample_doc)

        # Section A: from index 2 to index 5 (before Section B)
        assert by_name['Section A']['start'] == 2
        assert by_name['Section A']['end'] == 5

        # Section B: from index 5 to index 9 (includes B.1 subsection)
        assert by_name['Section B']['start'] == 5
        assert by_name['Section B']['end'] == 9

        # Section B.1 (h3): from index 7 to index 9 (before Section C which is h2)
        assert by_name['Section B.1']['start'] == 7
        assert by_name['Section B.1']['end'] == 9

    def test_empty_doc(self):
        assert find_sections([]) == []

    def test_no_headings(self):
        assert find_sections([para("just text")]) == []


# ---------------------------------------------------------------------------
# extract_section
# ---------------------------------------------------------------------------

class TestExtractSection:
    def test_extract_by_exact_name(self, sample_doc):
        nodes = extract_section(sample_doc, "Section A")
        assert len(nodes) == 3  # heading + 2 paragraphs
        assert nodes[0]['type'] == 'heading'

    def test_extract_case_insensitive(self, sample_doc):
        nodes = extract_section(sample_doc, "section a")
        assert nodes is not None
        assert len(nodes) == 3

    def test_extract_substring_match(self, sample_doc):
        nodes = extract_section(sample_doc, "B.1")
        assert nodes is not None
        assert len(nodes) == 2  # heading + paragraph

    def test_extract_not_found(self, sample_doc):
        assert extract_section(sample_doc, "Nonexistent") is None

    def test_extract_includes_subsections(self, sample_doc):
        nodes = extract_section(sample_doc, "Section B")
        # B heading + B para + B.1 heading + B.1 para = 4
        assert len(nodes) == 4


# ---------------------------------------------------------------------------
# replace_section
# ---------------------------------------------------------------------------

class TestReplaceSection:
    def test_replace_section(self, sample_doc):
        new = [heading(2, "Section A"), para("Replaced!")]
        result = replace_section(sample_doc, "Section A", new)
        # Original was 11 nodes, Section A was 3 nodes (indices 2-4), replaced with 2
        assert len(result) == 10
        # Check the replacement is in place
        md = adf_to_markdown(result)
        assert 'Replaced!' in md
        assert 'Content of section A' not in md
        # Other sections untouched
        assert 'Content of section B' in md
        assert 'Content of section C' in md

    def test_replace_not_found(self, sample_doc):
        with pytest.raises(ValueError, match='Section not found'):
            replace_section(sample_doc, "Nonexistent", [para("x")])


# ---------------------------------------------------------------------------
# insert_after
# ---------------------------------------------------------------------------

class TestInsertAfter:
    def test_insert_after_section(self, sample_doc):
        new = [heading(2, "Section A.5"), para("Inserted!")]
        result = insert_after(sample_doc, "Section A", new)
        assert len(result) == len(sample_doc) + 2
        md = adf_to_markdown(result)
        assert 'Inserted!' in md
        # Original content preserved
        assert 'Content of section A' in md
        assert 'Content of section B' in md

    def test_insert_not_found(self, sample_doc):
        with pytest.raises(ValueError, match='Section not found'):
            insert_after(sample_doc, "Nonexistent", [para("x")])


# ---------------------------------------------------------------------------
# Extensions (bodiedExtension)
# ---------------------------------------------------------------------------

def _make_extension(title, key='panelbox', content=None):
    """Helper to create a bodiedExtension node for testing."""
    if content is None:
        content = [para(f"Content of {title}")]
    return {
        'type': 'bodiedExtension',
        'attrs': {
            'layout': 'default',
            'extensionType': 'com.atlassian.confluence.macro.core',
            'extensionKey': key,
            'parameters': {
                'macroParams': {
                    'id': {'value': '4'},
                    'title': {'value': title},
                },
                'macroMetadata': {'macroId': {'value': 'test-id'}, 'schemaVersion': {'value': '1'}},
            },
            'localId': 'test-local-id',
        },
        'content': content,
    }


@pytest.fixture
def doc_with_extensions():
    """A doc with bodiedExtension nodes mixed with regular content."""
    return [
        _make_extension("In Scope Controls", content=[bullet_list(["5.15", "5.16"])]),
        _make_extension("References", key='panelbox'),
        heading(2, "Introduction"),
        para("Some text."),
    ]


class TestFindExtensions:
    def test_finds_all(self, doc_with_extensions):
        exts = find_extensions(doc_with_extensions)
        assert len(exts) == 2
        assert exts[0]['title'] == 'In Scope Controls'
        assert exts[0]['key'] == 'panelbox'
        assert exts[0]['index'] == 0
        assert exts[1]['title'] == 'References'
        assert exts[1]['index'] == 1

    def test_empty_doc(self):
        assert find_extensions([]) == []

    def test_no_extensions(self):
        assert find_extensions([para("just text"), heading(2, "H")]) == []


class TestExtractExtension:
    def test_extract_by_title(self, doc_with_extensions):
        node = extract_extension(doc_with_extensions, "In Scope Controls")
        assert node is not None
        assert node['type'] == 'bodiedExtension'
        assert node['content'][0]['type'] == 'bulletList'

    def test_extract_case_insensitive(self, doc_with_extensions):
        node = extract_extension(doc_with_extensions, "references")
        assert node is not None

    def test_extract_substring(self, doc_with_extensions):
        node = extract_extension(doc_with_extensions, "Scope")
        assert node is not None
        assert 'In Scope Controls' in str(node)

    def test_extract_not_found(self, doc_with_extensions):
        assert extract_extension(doc_with_extensions, "Nonexistent") is None


class TestReplaceExtension:
    def test_replace_content(self, doc_with_extensions):
        new_content = [bullet_list(["5.15", "5.16", "5.17"])]
        result = replace_extension(doc_with_extensions, "In Scope Controls", new_content)
        assert len(result) == len(doc_with_extensions)
        # The extension wrapper is preserved
        assert result[0]['type'] == 'bodiedExtension'
        assert result[0]['attrs']['parameters']['macroParams']['title']['value'] == 'In Scope Controls'
        # Content is replaced
        assert len(result[0]['content'][0]['content']) == 3  # 3 list items now

    def test_replace_preserves_others(self, doc_with_extensions):
        new_content = [para("Updated")]
        result = replace_extension(doc_with_extensions, "References", new_content)
        # First extension untouched
        assert result[0]['content'][0]['type'] == 'bulletList'
        # Second extension content replaced
        assert result[1]['content'] == [para("Updated")]
        # Regular content untouched
        assert result[2]['type'] == 'heading'

    def test_replace_not_found(self, doc_with_extensions):
        with pytest.raises(ValueError, match='Extension not found'):
            replace_extension(doc_with_extensions, "Nonexistent", [para("x")])


class TestAdfToMarkdownExtensions:
    def test_renders_extension_content(self, doc_with_extensions):
        md = adf_to_markdown(doc_with_extensions)
        assert 'panelbox: In Scope Controls' in md
        assert '5.15' in md
        assert 'panelbox: References' in md
        assert 'Introduction' in md


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

class TestBuilders:
    def test_heading(self):
        h = heading(2, "Test")
        assert h['type'] == 'heading'
        assert h['attrs']['level'] == 2
        assert h['content'][0]['text'] == 'Test'

    def test_heading_with_inline_nodes(self):
        h = heading(3, [bold("Bold"), text(" heading")])
        assert len(h['content']) == 2

    def test_para_strings(self):
        p = para("hello", "world")
        assert p['type'] == 'paragraph'
        assert len(p['content']) == 2
        assert all(n['type'] == 'text' for n in p['content'])

    def test_para_mixed(self):
        p = para("plain ", bold("bold"), " text")
        assert len(p['content']) == 3
        assert p['content'][1]['marks'] == [{'type': 'strong'}]

    def test_text_marks(self):
        t = text("test", bold=True, italic=True, code=True)
        mark_types = [m['type'] for m in t['marks']]
        assert 'strong' in mark_types
        assert 'em' in mark_types
        assert 'code' in mark_types

    def test_text_link(self):
        t = text("click", link="https://example.com")
        assert t['marks'][0]['type'] == 'link'
        assert t['marks'][0]['attrs']['href'] == 'https://example.com'

    def test_text_color(self):
        t = text("red", color='#ff0000')
        assert t['marks'][0]['attrs']['color'] == '#ff0000'

    def test_status_badge(self):
        s = status_badge("DONE", "green")
        assert s['type'] == 'status'
        assert s['attrs']['text'] == 'DONE'
        assert s['attrs']['color'] == 'green'

    def test_bullet_list_strings(self):
        bl = bullet_list(["a", "b"])
        assert bl['type'] == 'bulletList'
        assert len(bl['content']) == 2
        assert bl['content'][0]['type'] == 'listItem'

    def test_bullet_list_inline_nodes(self):
        bl = bullet_list([[bold("bold"), text(" item")], "plain item"])
        assert len(bl['content']) == 2

    def test_ordered_list(self):
        ol = ordered_list(["first", "second"])
        assert ol['type'] == 'orderedList'
        assert ol['attrs']['order'] == 1

    def test_table(self):
        t = table(["H1", "H2"], [["a", "b"], ["c", "d"]])
        assert t['type'] == 'table'
        assert len(t['content']) == 3  # 1 header row + 2 data rows
        assert t['content'][0]['content'][0]['type'] == 'tableHeader'
        assert t['content'][1]['content'][0]['type'] == 'tableCell'

    def test_panel(self):
        p = panel("warning", [para("Watch out!")])
        assert p['type'] == 'panel'
        assert p['attrs']['panelType'] == 'warning'

    def test_code_block(self):
        cb = code_block("print('hello')", "python")
        assert cb['type'] == 'codeBlock'
        assert cb['attrs']['language'] == 'python'

    def test_expand(self):
        e = expand("Details", [para("Hidden content")])
        assert e['type'] == 'expand'
        assert e['attrs']['title'] == 'Details'

    def test_rule(self):
        assert rule()['type'] == 'rule'


# ---------------------------------------------------------------------------
# md_to_adf
# ---------------------------------------------------------------------------

class TestMdToAdf:
    def test_heading(self):
        nodes = md_to_adf("## Hello World")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'heading'
        assert nodes[0]['attrs']['level'] == 2

    def test_paragraph(self):
        nodes = md_to_adf("Just some text.")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'paragraph'

    def test_bold(self):
        nodes = md_to_adf("This is **bold** text.")
        p = nodes[0]
        assert any(
            n.get('marks', [{}])[0].get('type') == 'strong'
            for n in p['content'] if n.get('marks')
        )

    def test_italic(self):
        nodes = md_to_adf("This is *italic* text.")
        p = nodes[0]
        assert any(
            n.get('marks', [{}])[0].get('type') == 'em'
            for n in p['content'] if n.get('marks')
        )

    def test_inline_code(self):
        nodes = md_to_adf("Use `code` here.")
        p = nodes[0]
        assert any(
            any(m.get('type') == 'code' for m in n.get('marks', []))
            for n in p['content']
        )

    def test_link(self):
        nodes = md_to_adf("Click [here](https://example.com).")
        p = nodes[0]
        assert any(
            any(m.get('type') == 'link' for m in n.get('marks', []))
            for n in p['content']
        )

    def test_bullet_list(self):
        nodes = md_to_adf("- one\n- two\n- three")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'bulletList'
        assert len(nodes[0]['content']) == 3

    def test_ordered_list(self):
        nodes = md_to_adf("1. first\n2. second")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'orderedList'
        assert len(nodes[0]['content']) == 2

    def test_horizontal_rule(self):
        nodes = md_to_adf("above\n\n---\n\nbelow")
        types = [n['type'] for n in nodes]
        assert 'rule' in types

    def test_code_block(self):
        md = "```python\nprint('hello')\n```"
        nodes = md_to_adf(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'codeBlock'
        assert nodes[0]['attrs']['language'] == 'python'

    def test_blockquote(self):
        nodes = md_to_adf("> quoted text")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'blockquote'

    def test_blank_lines_ignored(self):
        nodes = md_to_adf("\n\nHello\n\n\nWorld\n\n")
        assert len(nodes) == 2  # two paragraphs

    def test_mixed_content(self):
        md = """## Title

Some intro text with **bold**.

- bullet one
- bullet two

---

## Another Section

More text.
"""
        nodes = md_to_adf(md)
        types = [n['type'] for n in nodes]
        assert types == ['heading', 'paragraph', 'bulletList', 'rule', 'heading', 'paragraph']

    def test_roundtrip_readable(self):
        """md_to_adf output should produce readable markdown via atlas-doc-parser."""
        md_in = "## Test\n\nHello **world** with a [link](https://x.com).\n\n- item one\n- item two"
        nodes = md_to_adf(md_in)
        md_out = adf_to_markdown(nodes)
        assert 'Test' in md_out
        assert 'world' in md_out
        assert 'item one' in md_out
