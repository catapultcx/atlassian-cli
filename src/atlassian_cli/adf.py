"""ADF (Atlassian Document Format) utilities for section-level editing.

Reading uses atlas-doc-parser (ADF → markdown).
Building and editing are handled here.

Provides:
    adf_to_markdown    Convert ADF doc/nodes to markdown (via atlas-doc-parser)
    md_to_adf          Convert markdown string to ADF node list
    find_sections      List headings with node index ranges
    extract_section    Get ADF nodes for one section by heading text
    replace_section    Splice new nodes into a section
    insert_after       Insert nodes after a section
    find_extensions    List bodiedExtension nodes (macros/addons) with index and title
    extract_extension  Get a bodiedExtension node by title
    replace_extension  Replace the content inside a bodiedExtension by title
    Builder funcs      heading(), para(), text(), bold(), table(), etc.
"""

import re
import uuid

from atlas_doc_parser.api import NodeDoc

# ---------------------------------------------------------------------------
# ADF → markdown  (delegates to atlas-doc-parser)
# ---------------------------------------------------------------------------

def adf_to_markdown(adf):
    """Convert an ADF document or node list to markdown.

    Accepts either a full ADF doc ``{"type": "doc", "content": [...]}``
    or a plain list of ADF nodes.

    Handles bodiedExtension nodes (third-party macros) by rendering their
    content with a ``[macro: Title]`` prefix, since atlas-doc-parser drops them.
    """
    if isinstance(adf, list):
        nodes = adf
    else:
        nodes = adf.get('content', [])

    # Pre-process: expand bodiedExtension nodes so atlas-doc-parser can render the content
    expanded = _expand_extensions(nodes)
    doc = NodeDoc.from_dict({'type': 'doc', 'version': 1, 'content': expanded})
    return doc.to_markdown()


def _expand_extensions(nodes):
    """Replace bodiedExtension nodes with renderable equivalents.

    Inserts a bold paragraph ``[extensionKey: Title]`` followed by the
    extension's content nodes, so they appear in markdown output.
    """
    result = []
    for node in nodes:
        if isinstance(node, dict) and node.get('type') == 'bodiedExtension':
            title = _extension_title(node)
            key = node.get('attrs', {}).get('extensionKey', 'macro')
            label = f'[{key}: {title}]' if title else f'[{key}]'
            result.append({
                'type': 'paragraph',
                'content': [{'type': 'text', 'text': label, 'marks': [{'type': 'strong'}]}],
            })
            result.extend(node.get('content', []))
        else:
            result.append(node)
    return result


# ---------------------------------------------------------------------------
# Sections — find, extract, replace, insert
# ---------------------------------------------------------------------------

def _heading_text(node):
    """Extract plain text from a heading node's content."""
    parts = []
    for child in node.get('content', []):
        if child.get('type') == 'text':
            parts.append(child.get('text', ''))
    return ''.join(parts).strip()


def find_sections(nodes):
    """Return list of sections: [{heading, level, start, end}, ...].

    Each section spans from its heading node to (but not including) the next
    heading of equal or higher level, or end of document.
    ``nodes`` is the top-level content array of an ADF doc.
    """
    headings = []
    for i, node in enumerate(nodes):
        if isinstance(node, dict) and node.get('type') == 'heading':
            level = node.get('attrs', {}).get('level', 1)
            headings.append({'heading': _heading_text(node), 'level': level, 'start': i})

    sections = []
    for idx, h in enumerate(headings):
        end = len(nodes)
        for j in range(idx + 1, len(headings)):
            if headings[j]['level'] <= h['level']:
                end = headings[j]['start']
                break
        sections.append({
            'heading': h['heading'],
            'level': h['level'],
            'start': h['start'],
            'end': end,
        })
    return sections


def _find_section(nodes, heading_text):
    """Find a section by heading text (case-insensitive substring match)."""
    query = heading_text.lower()
    for section in find_sections(nodes):
        if query in section['heading'].lower():
            return section
    return None


def extract_section(nodes, heading_text):
    """Return the ADF nodes for a section (heading + body), or None."""
    section = _find_section(nodes, heading_text)
    if not section:
        return None
    return nodes[section['start']:section['end']]


def replace_section(nodes, heading_text, new_nodes):
    """Replace a section's nodes with new_nodes. Returns new node list.

    Raises ValueError if section not found.
    """
    section = _find_section(nodes, heading_text)
    if not section:
        raise ValueError(f'Section not found: {heading_text}')
    return nodes[:section['start']] + new_nodes + nodes[section['end']:]


def insert_after(nodes, heading_text, new_nodes):
    """Insert new_nodes after a section. Returns new node list.

    Raises ValueError if section not found.
    """
    section = _find_section(nodes, heading_text)
    if not section:
        raise ValueError(f'Section not found: {heading_text}')
    return nodes[:section['end']] + new_nodes + nodes[section['end']:]


# ---------------------------------------------------------------------------
# Extensions (bodiedExtension) — find, extract, replace
# ---------------------------------------------------------------------------

def _extension_title(node):
    """Extract the title from a bodiedExtension node's macroParams."""
    try:
        return node['attrs']['parameters']['macroParams']['title']['value']
    except (KeyError, TypeError):
        return ''


def find_extensions(nodes):
    """Return list of bodiedExtension nodes: [{title, key, index}, ...].

    ``nodes`` is the top-level content array of an ADF doc.
    """
    results = []
    for i, node in enumerate(nodes):
        if isinstance(node, dict) and node.get('type') == 'bodiedExtension':
            key = node.get('attrs', {}).get('extensionKey', '')
            results.append({
                'title': _extension_title(node),
                'key': key,
                'index': i,
            })
    return results


def _find_extension(nodes, title):
    """Find a bodiedExtension by title (case-insensitive substring match)."""
    query = title.lower()
    for ext in find_extensions(nodes):
        if query in ext['title'].lower():
            return ext
    return None


def extract_extension(nodes, title):
    """Return the bodiedExtension node matching title, or None."""
    ext = _find_extension(nodes, title)
    if not ext:
        return None
    return nodes[ext['index']]


def replace_extension(nodes, title, new_content):
    """Replace the content inside a bodiedExtension. Returns new node list.

    Only replaces the ``content`` array inside the extension node —
    the wrapper (attrs, macroParams, styling) is preserved.
    Raises ValueError if extension not found.
    """
    ext = _find_extension(nodes, title)
    if not ext:
        raise ValueError(f'Extension not found: {title}')
    idx = ext['index']
    updated = dict(nodes[idx])
    updated['content'] = new_content
    return nodes[:idx] + [updated] + nodes[idx + 1:]


# ---------------------------------------------------------------------------
# ADF node builders
# ---------------------------------------------------------------------------

def heading(level, content):
    """Create a heading node. content: string or list of inline nodes."""
    if isinstance(content, str):
        content = [text(content)]
    return {'type': 'heading', 'attrs': {'level': level}, 'content': content}


def para(*inlines):
    """Create a paragraph from inline nodes or strings."""
    content = []
    for item in inlines:
        content.append(text(item) if isinstance(item, str) else item)
    return {'type': 'paragraph', 'content': content}


def text(t, bold=False, italic=False, strike=False, code=False, link=None, color=None):
    """Create a text node with optional marks."""
    node = {'type': 'text', 'text': t}
    marks = []
    if bold:
        marks.append({'type': 'strong'})
    if italic:
        marks.append({'type': 'em'})
    if strike:
        marks.append({'type': 'strike'})
    if code:
        marks.append({'type': 'code'})
    if link:
        marks.append({'type': 'link', 'attrs': {'href': link}})
    if color:
        marks.append({'type': 'textColor', 'attrs': {'color': color}})
    if marks:
        node['marks'] = marks
    return node


def bold(t):
    """Shorthand for bold text node."""
    return text(t, bold=True)


def italic(t):
    """Shorthand for italic text node."""
    return text(t, italic=True)


def link(label, href):
    """Shorthand for a link text node."""
    return text(label, link=href)


def status_badge(label, color='neutral'):
    """Create a status lozenge. Colors: neutral, purple, blue, green, yellow, red."""
    return {'type': 'status', 'attrs': {'text': label, 'color': color, 'localId': '', 'style': ''}}


def hard_break():
    return {'type': 'hardBreak'}


def rule():
    return {'type': 'rule'}


def bullet_list(items):
    """Create a bullet list. Items: strings, inline-node lists, or listItem dicts."""
    return {'type': 'bulletList', 'content': [_to_list_item(item) for item in items]}


def ordered_list(items):
    """Create a numbered list. Items same as bullet_list."""
    return {'type': 'orderedList', 'attrs': {'order': 1}, 'content': [_to_list_item(item) for item in items]}


def _to_list_item(item):
    if isinstance(item, dict) and item.get('type') == 'listItem':
        return item
    if isinstance(item, str):
        return {'type': 'listItem', 'content': [para(item)]}
    if isinstance(item, list):
        return {'type': 'listItem', 'content': [para(*item)]}
    return {'type': 'listItem', 'content': [para(str(item))]}


def table(header_cells, rows, *, colwidths=None, localid=None):
    """Create a table. header_cells/rows: lists of strings or inline-node lists.

    Args:
        header_cells: Column headings (strings or inline-node lists).
        rows: Body rows, each a list of cell values.
        colwidths: Optional list of column widths (int/float). If omitted,
                   divides 900 equally.
        localid: Optional table-level UUID. If omitted, generated.
    """
    n_cols = len(header_cells)
    if colwidths is None:
        colwidths = [round(900.0 / n_cols, 1)] * n_cols

    def _uuid():
        return str(uuid.uuid4())

    def cell(val, col_idx, is_header=False, row_localid=None):
        ct = 'tableHeader' if is_header else 'tableCell'
        colwidth = colwidths[col_idx] if col_idx < len(colwidths) else colwidths[-1]
        attrs = {'colspan': 1, 'colwidth': colwidth, 'rowspan': 1}
        if isinstance(val, str):
            content_nodes = [para(val)]
        elif isinstance(val, list):
            content_nodes = [para(*val)]
        else:
            content_nodes = [para(str(val))]
        node = {
            'type': ct,
            'attrs': attrs,
            'content': content_nodes,
            'localId': _uuid(),
        }
        return node

    tbl_localid = localid or _uuid()

    content = [
        {
            'type': 'tableRow',
            'content': [cell(c, ci, is_header=True) for ci, c in enumerate(header_cells)],
            'localId': _uuid(),
        }
    ]
    for ri, row in enumerate(rows):
        row_localid = _uuid()
        cells = []
        for ci, c in enumerate(row):
            cells.append(cell(c, ci, is_header=False))
        content.append({
            'type': 'tableRow',
            'content': cells,
            'localId': row_localid,
        })
    return {
        'type': 'table',
        'attrs': {'isNumberColumnEnabled': False, 'layout': 'default', 'localId': tbl_localid},
        'content': content,
    }


def panel(panel_type, content_nodes):
    """Create a panel. panel_type: info, note, warning, success, error."""
    return {'type': 'panel', 'attrs': {'panelType': panel_type}, 'content': content_nodes}


def code_block(code_text, language=''):
    return {'type': 'codeBlock', 'attrs': {'language': language}, 'content': [text(code_text)]}


def expand(title, content_nodes):
    return {'type': 'expand', 'attrs': {'title': title}, 'content': content_nodes}


def blockquote(content_nodes):
    return {'type': 'blockquote', 'content': content_nodes}


# ---------------------------------------------------------------------------
# Markdown → ADF
# ---------------------------------------------------------------------------

def md_to_adf(markdown):
    """Convert a markdown string to a list of ADF nodes.

    Supports: headings, paragraphs, bullet/ordered lists, bold, italic,
    bold+italic, inline code, links, horizontal rules, code blocks, blockquotes,
    tables (newline-separated and inline-flattened forms).
    """
    lines = markdown.split('\n')
    nodes = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        # Horizontal rule
        if re.match(r'^---+\s*$', line):
            nodes.append(rule())
            i += 1
            continue

        # Heading
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            nodes.append(heading(len(m.group(1)), _parse_inline(m.group(2).strip())))
            i += 1
            continue

        # Code block
        if line.strip().startswith('```'):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1
            nodes.append(code_block('\n'.join(code_lines), lang))
            continue

        # Blockquote
        if line.startswith('> '):
            bq_lines = []
            while i < len(lines) and lines[i].startswith('> '):
                bq_lines.append(lines[i][2:])
                i += 1
            nodes.append(blockquote(md_to_adf('\n'.join(bq_lines))))
            continue

        # Bullet list
        if re.match(r'^[-*]\s', line):
            items = []
            while i < len(lines) and re.match(r'^[-*]\s', lines[i]):
                items.append(_parse_inline(re.sub(r'^[-*]\s+', '', lines[i])))
                i += 1
            nodes.append({'type': 'bulletList', 'content': [
                {'type': 'listItem', 'content': [{'type': 'paragraph', 'content': inlines}]}
                for inlines in items
            ]})
            continue

        # Ordered list
        if re.match(r'^\d+\.\s', line):
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s', lines[i]):
                items.append(_parse_inline(re.sub(r'^\d+\.\s+', '', lines[i])))
                i += 1
            nodes.append({'type': 'orderedList', 'attrs': {'order': 1}, 'content': [
                {'type': 'listItem', 'content': [{'type': 'paragraph', 'content': inlines}]}
                for inlines in items
            ]})
            continue

        # Table (newline-separated Form A)
        if line.startswith('|'):
            tbl_result = _try_parse_table(lines, i)
            if tbl_result:
                nodes.append(tbl_result[0])
                i = tbl_result[1]
                continue

        # Paragraph — consecutive non-blank, non-block lines
        para_lines = []
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            joined = ' '.join(para_lines)
            # Table (inline-flattened Form B) — detect inside paragraph
            if _looks_like_inline_table(joined):
                tbl_node = _parse_inline_table(joined)
                if tbl_node:
                    nodes.append(tbl_node)
                    continue
            nodes.append({'type': 'paragraph', 'content': _parse_inline(joined)})

    return nodes


_SEP_RE = re.compile(r'^:?-+:?$')


def _is_separator_row(cell_texts):
    """Return True if every non-empty cell matches the separator pattern."""
    return all(_SEP_RE.match(c.strip()) for c in cell_texts if c.strip())


def _split_row(line):
    """Split a ``|...|...|`` markdown table row into cell strings."""
    parts = line.strip().split('|')
    # first and last are empty (leading/trailing pipe)
    if parts and parts[0] == '':
        parts = parts[1:]
    if parts and parts[-1] == '':
        parts = parts[:-1]
    return [p.strip() for p in parts]


def _looks_like_inline_table(text_str):
    """Check if a single-line paragraph looks like a flattened markdown table."""
    # Must contain a separator pattern: |---| somewhere
    if not re.search(r'\|\s*:?-{3,}:?\s*\|', text_str):
        return False
    # Must have at least 2 pipes (3 cells minimum after split)
    return text_str.count('|') >= 4


def _parse_inline_table(text_str):
    """Parse an inline-flattened markdown table into an ADF table node.

    Row boundaries are ``|`` followed by whitespace then ``|`` (closing pipe
    of one row immediately followed by opening pipe of the next).
    """
    raw_rows = re.split(r'\|\s+(?=\|)', text_str)
    return _build_table_from_rows(raw_rows)


def _try_parse_table(lines, start):
    """Try to parse a newline-separated markdown table starting at *start*.

    Returns ``(table_node, new_index)`` or ``None`` if not a valid table.
    """
    i = start
    raw_rows = []
    while i < len(lines) and lines[i].strip().startswith('|'):
        raw_rows.append(lines[i].strip())
        i += 1

    if len(raw_rows) < 2:
        return None
    # The second row must be a separator
    cells = _split_row(raw_rows[1])
    if not _is_separator_row(cells):
        return None

    return _build_table_from_rows(raw_rows), i


def _build_table_from_rows(raw_rows):
    """Build an ADF table node from a list of ``|...|`` row strings.

    First row = header, second row = separator (dropped), remainder = body.
    """
    if len(raw_rows) < 2:
        return None

    header_cells = _split_row(raw_rows[0])
    n_cols = len(header_cells)

    body_cells = []
    for ri in range(2, len(raw_rows)):
        row = _split_row(raw_rows[ri])
        if not any(r.strip() for r in row):
            continue
        if len(row) < n_cols:
            row.extend([''] * (n_cols - len(row)))
        elif len(row) > n_cols:
            row = row[:n_cols]
        body_cells.append(row)

    # Parse inline content for header cells, add strong mark
    parsed_header = []
    for h in header_cells:
        inlines = _parse_inline(h)
        for node in inlines:
            if node.get('type') == 'text':
                node.setdefault('marks', []).insert(0, {'type': 'strong'})
        parsed_header.append(inlines)

    parsed_body = []
    for row in body_cells:
        parsed_body.append([_parse_inline(c) for c in row])

    return table(parsed_header, parsed_body)


def _is_block_start(line):
    if re.match(r'^#{1,6}\s', line):
        return True
    if re.match(r'^[-*]\s', line):
        return True
    if re.match(r'^\d+\.\s', line):
        return True
    if line.strip().startswith('```'):
        return True
    if re.match(r'^---+\s*$', line):
        return True
    if line.startswith('> '):
        return True
    return False


def _parse_inline(text_str):
    """Parse inline markdown (bold, italic, code, links) into ADF inline nodes."""
    nodes = []
    pattern = re.compile(
        r'\*\*\*(.+?)\*\*\*'           # ***bold italic***
        r'|\*\*(.+?)\*\*'              # **bold**
        r'|\*(.+?)\*'                  # *italic*
        r'|`(.+?)`'                    # `code`
        r'|\[([^\]]+)\]\(([^)]+)\)'    # [text](url)
    )

    last_end = 0
    for m in pattern.finditer(text_str):
        if m.start() > last_end:
            nodes.append(text(text_str[last_end:m.start()]))

        if m.group(1) is not None:
            nodes.append({'type': 'text', 'text': m.group(1), 'marks': [{'type': 'strong'}, {'type': 'em'}]})
        elif m.group(2) is not None:
            nodes.append(bold(m.group(2)))
        elif m.group(3) is not None:
            nodes.append(italic(m.group(3)))
        elif m.group(4) is not None:
            nodes.append(text(m.group(4), code=True))
        elif m.group(5) is not None:
            nodes.append(link(m.group(5), m.group(6)))

        last_end = m.end()

    if last_end < len(text_str):
        nodes.append(text(text_str[last_end:]))

    if not nodes:
        nodes.append(text(text_str))

    return nodes
