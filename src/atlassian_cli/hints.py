"""Embedded hints for AI agents working with Confluence ADF.

This module provides structured guidance that AI agents can query to understand
how to work with ADF documents, third-party macros, and common page patterns.

Usage:
    from atlassian_cli.hints import get_hints, get_hint
    all_hints = get_hints()          # all hints as a dict
    macro_hint = get_hint('macros')  # one topic
"""

HINTS = {
    'macros': {
        'summary': 'Third-party macros appear as bodiedExtension nodes in ADF.',
        'detail': (
            'bodiedExtension nodes wrap third-party Confluence macros (addons). '
            'The extensionKey identifies the macro type. The content array holds '
            'standard ADF nodes. When editing, preserve the full wrapper (attrs, '
            'parameters, localId) and only modify the content array inside. '
            'Use find_extensions() and replace_extension() from atlassian_cli.adf.'
        ),
        'structure': {
            'type': 'bodiedExtension',
            'attrs': {
                'layout': 'default',
                'extensionType': 'com.atlassian.confluence.macro.core',
                'extensionKey': '<macro-key e.g. panelbox, details>',
                'parameters': {
                    'macroParams': {
                        '<param-name>': {'value': '<param-value>'},
                    },
                    'macroMetadata': {
                        'macroId': {'value': '<uuid>'},
                        'schemaVersion': {'value': '1'},
                    },
                },
                'localId': '<uuid>',
            },
            'content': ['<standard ADF nodes>'],
        },
        'known_macros': {
            'panelbox': {
                'description': 'Styled panel box (Advanced Panelboxes by bitvoodoo/communardo).',
                'params': ['id (style ID)', 'title'],
                'notes': (
                    'The id param controls visual style, not identity. '
                    'Generate fresh UUIDs for macroId and localId when creating new ones.'
                ),
            },
            'details': {
                'description': 'Metadata/details section, usually contains tables.',
                'params': ['_parentId (optional)'],
                'notes': 'Typically has no title param. Preserve as-is when editing.',
            },
        },
    },
    'sections': {
        'summary': 'Sections are defined by heading nodes and used as the unit of editing.',
        'detail': (
            'Use find_sections() to list all sections with their heading text, level, '
            'and node index range. Sections span from their heading to the next heading '
            'of equal or higher level. Use extract_section(), replace_section(), and '
            'insert_after() for safe, targeted edits without touching the rest of the page.'
        ),
    },
    'editing': {
        'summary': 'Best practices for editing Confluence pages via ADF.',
        'rules': [
            'Always read the page first (confluence get) to get the current version.',
            'Use section-level or extension-level operations, never rewrite the whole page.',
            'Preserve all bodiedExtension wrappers — only modify their content arrays.',
            'Do not rename or restyle existing panelboxes, tables, or macros unless asked.',
            'The put command checks version numbers to prevent conflicts.',
            'Use adf_to_markdown() to preview changes before uploading.',
        ],
    },
    'adf_basics': {
        'summary': 'ADF (Atlassian Document Format) is the JSON tree structure used by Confluence.',
        'detail': (
            'An ADF document has type "doc" with a content array of block nodes. '
            'Block nodes include: paragraph, heading, bulletList, orderedList, table, '
            'panel, codeBlock, blockquote, expand, rule, bodiedExtension. '
            'Inline nodes (inside paragraphs/headings) include: text, hardBreak, '
            'inlineCard, status. Text nodes can have marks: strong, em, strike, code, '
            'link, textColor.'
        ),
        'builders': (
            'Use the builder functions in atlassian_cli.adf: heading(), para(), text(), '
            'bold(), italic(), link(), bullet_list(), ordered_list(), table(), panel(), '
            'code_block(), expand(), blockquote(), rule(), status_badge(), hard_break(). '
            'Use md_to_adf() to convert markdown to ADF nodes for simple content.'
        ),
    },
}


def get_hints():
    """Return all hints as a dict."""
    return HINTS


def get_hint(topic):
    """Return hints for a specific topic, or None."""
    return HINTS.get(topic)


def format_hints(topic=None):
    """Format hints as readable text for CLI output."""
    topics = {topic: HINTS[topic]} if topic and topic in HINTS else HINTS
    lines = []
    for name, data in topics.items():
        lines.append(f'## {name}')
        lines.append(f'  {data.get("summary", "")}')
        if 'detail' in data:
            lines.append(f'  {data["detail"]}')
        if 'rules' in data:
            for r in data['rules']:
                lines.append(f'  - {r}')
        if 'builders' in data:
            lines.append(f'  {data["builders"]}')
        if 'known_macros' in data:
            for mk, mv in data['known_macros'].items():
                lines.append(f'  [{mk}] {mv["description"]}')
                lines.append(f'    params: {", ".join(mv["params"])}')
                lines.append(f'    {mv["notes"]}')
        if 'structure' in data:
            lines.append('  Structure: (use --json for machine-readable output)')
        lines.append('')
    return '\n'.join(lines)
