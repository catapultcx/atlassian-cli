"""ADF (Atlassian Document Format) utilities for section-level editing.

Reading uses atlas-doc-parser (ADF → markdown).
Building and editing are handled here.

Provides:
    adf_to_markdown  Convert ADF doc/nodes to markdown (via atlas-doc-parser)
    md_to_adf        Convert markdown string to ADF node list
    find_sections    List headings with node index ranges
    extract_section  Get ADF nodes for one section by heading text
    replace_section  Splice new nodes into a section
    insert_after     Insert nodes after a section
    Builder funcs    heading(), para(), text(), bold(), table(), etc.
"""

import re

from atlas_doc_parser.api import NodeDoc


# ---------------------------------------------------------------------------
# ADF → markdown  (delegates to atlas-doc-parser)
# ---------------------------------------------------------------------------

def adf_to_markdown(adf):
    """Convert an ADF document or node list to markdown.

    Accepts either a full ADF doc ``{"type": "doc", "content": [...]}``
    or a plain list of ADF nodes.
    """
    if isinstance(adf, list):
        adf = {'type': 'doc', 'version': 1, 'content': adf}
    doc = NodeDoc.from_dict(adf)
    return doc.to_markdown()


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


def table(header_cells, rows):
    """Create a table. header_cells/rows: lists of strings or inline-node lists."""
    def cell(val, is_header=False):
        ct = 'tableHeader' if is_header else 'tableCell'
        if isinstance(val, str):
            return {'type': ct, 'attrs': {}, 'content': [para(val)]}
        if isinstance(val, list):
            return {'type': ct, 'attrs': {}, 'content': [para(*val)]}
        return {'type': ct, 'attrs': {}, 'content': [para(str(val))]}

    content = [{'type': 'tableRow', 'content': [cell(c, True) for c in header_cells]}]
    for row in rows:
        content.append({'type': 'tableRow', 'content': [cell(c) for c in row]})
    return {
        'type': 'table',
        'attrs': {'isNumberColumnEnabled': False, 'layout': 'default', 'localId': ''},
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
    bold+italic, inline code, links, horizontal rules, code blocks, blockquotes.
    Tables should use the table() builder instead.
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

        # Paragraph — consecutive non-blank, non-block lines
        para_lines = []
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            nodes.append({'type': 'paragraph', 'content': _parse_inline(' '.join(para_lines))})

    return nodes


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
