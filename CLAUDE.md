# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository or using the `atlassian-cli` package to edit Atlassian content.

## Quick Start

```bash
pip install atlassian-cli          # install from PyPI
pip install -e ".[dev]"            # or install from source with test/lint deps
pytest                              # run tests
ruff check src/ tests/              # lint
```

## Commands

Two entry points: `confluence` and `jira`. All commands accept `--json` for machine-readable output.

### Confluence

```bash
confluence get <page_id>                    # download page (ADF + meta)
confluence put <page_id> [--force] [-m msg]  # upload local edits
confluence delete <page_id>                 # delete a page
confluence diff <page_id>                   # compare local vs remote
confluence sync <space_key> [--workers 10]  # bulk-download space (parallel)
confluence search <query>                   # search local page-index.json
confluence index [--space <key> --space <key2>] # rebuild index from API (multiple spaces)
confluence hints [topic]                    # show ADF/macro editing guidance
```

### Jira Issues

```bash
jira issue get <key>
jira issue create <project> <type> <summary> [--description] [--labels] [--assignee] [--parent]
jira issue update <key> [--summary] [--description] [--labels] [--assignee] [--fields JSON]
jira issue delete <key>
jira issue search <jql> [--max 50]
jira issue transition <key> <status>
jira issue comment <key> <body>
jira issue comments <key>
```

### Jira Assets (JSM)

```bash
jira assets schemas                          # list schemas
jira assets types <schema_id>                # list object types
jira assets attrs <type_id>                  # list attributes
jira assets search <aql>                     # search with AQL
jira assets get <id>                         # get object
jira assets create <type_id> key=val ...     # create object
jira assets update <id> key=val ...          # update object
jira assets delete <id>                      # delete object
jira assets type-create <schema_id> <name>   # create object type
```

## Editing Confluence Pages

The workflow for editing Confluence pages is: **get -> edit locally -> put**.

### Step 1: Download the page

```bash
confluence get <page_id>
# saves pages/<SPACE>/<page_id>.json (ADF) and .meta.json (version, title)
```

### Step 2: Edit using the adf module

The `atlassian_cli.adf` module provides all editing functions. Use Python to make changes:

```python
import json
from atlassian_cli.adf import (
    # Reading
    adf_to_markdown,     # convert ADF to readable markdown
    find_sections,       # list all heading-based sections with index ranges
    find_extensions,     # list all bodiedExtension nodes (macros/addons)
    # Section operations
    extract_section,     # get ADF nodes for a section by heading text
    replace_section,     # replace a section's nodes
    insert_after,        # insert nodes after a section
    # Extension operations (for macros like panelbox, details)
    extract_extension,   # get a bodiedExtension node by title
    replace_extension,   # replace content inside an extension (preserves wrapper)
    # Builders
    heading, para, text, bold, italic, link,
    bullet_list, ordered_list, table,
    panel, code_block, expand, blockquote, rule,
    status_badge, hard_break,
    # Markdown to ADF
    md_to_adf,           # convert markdown string to ADF nodes
)

# Load page
with open('pages/<SPACE>/<page_id>.json') as f:
    doc = json.load(f)
content = doc['content']

# Preview as markdown
print(adf_to_markdown(content))

# List sections and extensions
for s in find_sections(content):
    print(f"L{s['level']} [{s['start']}:{s['end']}] {s['heading']}")
for e in find_extensions(content):
    print(f"[{e['index']}] {e['key']}: {e['title']}")

# Edit a section
new_nodes = [heading(2, "Updated Section"), para("New content.")]
content = replace_section(content, "Section Name", new_nodes)

# Edit a macro/extension (only replaces content, preserves wrapper)
new_content = [bullet_list(["Item 1", "Item 2"])]
content = replace_extension(content, "Extension Title", new_content)

# Save
doc['content'] = content
with open('pages/<SPACE>/<page_id>.json', 'w') as f:
    json.dump(doc, f, indent=2)
```

### Step 3: Upload

```bash
confluence put <page_id>
# checks version number to prevent conflicts; use --force to override
```

### Critical Editing Rules

1. **Always `get` first** — you need the current version number and full ADF
2. **Use section/extension operations** — never rewrite the whole page
3. **Preserve bodiedExtension wrappers** — only modify the `content` array inside macros, never change `attrs`, `parameters`, `localId`, or `macroId`
4. **Do not rename or restyle macros** — keep existing titles, IDs, and styles unless explicitly asked
5. **Preview before uploading** — use `adf_to_markdown()` to verify changes
6. **`put` checks versions** — if someone else edited the page, you'll get a conflict error

### Working with Macros (bodiedExtension nodes)

Third-party Confluence macros (like panelbox, details) appear as `bodiedExtension` nodes in ADF. The `adf_to_markdown()` function renders them as `**[extensionKey: Title]**` followed by their content.

Run `confluence hints macros` for the full macro reference, or use `--json` for machine-readable output.

Common macro: **panelbox** (Advanced Panelboxes by bitvoodoo/communardo)
- Styled panel boxes with a title bar
- The `id` macroParam controls visual style (instance-specific)
- Use `find_extensions()` to locate them, `replace_extension()` to edit content

### Text nodes with marks

```python
text("plain text")
text("bold", bold=True)
text("with link", link="https://example.com")
text("colored", color="#ff0000")
bold("shorthand bold")
italic("shorthand italic")
link("click here", "https://example.com")
```

### Inline cards (smart links)

To create a Confluence smart link (shows page title automatically):
```python
{"type": "inlineCard", "attrs": {"url": "https://your-site.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID"}}
```

## Architecture

```
src/atlassian_cli/
  config.py       .env parsing, auth, session factory — setup() returns (session, base_url)
  http.py         api_get/post/put/delete + APIError exception
  output.py       emit() with text/JSON modes, emit_error() to stderr
  confluence.py   Confluence CLI — API v2, ADF format, parallel sync
  adf.py          ADF utilities — section/extension ops, node builders, md conversion
  hints.py        Embedded hints for AI agents on ADF and macros
  jira.py         Jira CLI entry point — nested subparsers routing to:
  jira_issues.py  Issue CRUD — API v3, ADF for descriptions/comments
  jira_assets.py  Assets CRUD — Assets API v1, auto-discovers workspaceId
```

## APIs

| Service | Version | Base path |
|---------|---------|-----------|
| Confluence | v2 | `/wiki/api/v2/` |
| Jira | v3 | `/rest/api/3/` |
| Jira Assets | v1 | `api.atlassian.com/jsm/assets/workspace/{id}/v1` |

## Testing

Tests use `pytest` + `responses` for HTTP mocking. No live API calls.

```bash
pytest                        # all tests
pytest tests/test_confluence.py   # single module
pytest -k "test_search"       # by name
```

## Credentials

Set in `.env` or environment variables:
```
ATLASSIAN_URL=https://your-site.atlassian.net
ATLASSIAN_EMAIL=you@example.com
ATLASSIAN_TOKEN=your-api-token
```
Falls back to `CONFLUENCE_*` prefix for backward compat.
