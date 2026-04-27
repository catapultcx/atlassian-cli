# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test

```bash
pip install -e ".[dev]"            # install from source with test/lint deps
pytest                              # run all tests
pytest tests/test_confluence.py    # single module
pytest -k "test_search"            # by name pattern
ruff check src/ tests/              # lint (line-length=120, target py310)
```

## Commands

Two entry points: `confluence` and `jira`. All commands accept `--json` for machine-readable output.

### Confluence

```bash
confluence create <space> <title> [--body|--file] [--parent ID]  # create page
confluence get <page_id>                    # download page (ADF + meta)
confluence put <page_id> [--force] [-m msg]  # upload local edits
confluence delete <page_id>                 # delete a page
confluence diff <page_id>                   # compare local vs remote
confluence sync <space_key> [--workers 10]  # bulk-download space (parallel)
confluence search <query>                   # search local page-index.json
confluence index [--space <key> --space <key2>] # rebuild index from API (multiple spaces)
confluence comments <page_id> [--open]       # list comments on a page
confluence comment <comment_id> <body> [--footer]  # reply to a comment
confluence resolve <comment_id> [--reopen]  # resolve/reopen inline comment
confluence changes <page_id> [--version N]  # show what changed in latest version
confluence approvals [--spaces KEY ...]     # list pages pending your approval
confluence approve <page_id>               # approve a page
confluence reject <page_id>                # reject a page approval
confluence hints [topic]                    # show ADF/macro editing guidance
```

### Jira Issues

```bash
jira issue get <key>
jira issue create <project> <type> <summary> [--description] [--labels] [--assignee] [--parent]
jira issue update <key> [--summary] [--description] [--labels] [--assignee] [--fields JSON]
jira issue delete <key>
jira issue search <jql> [--max 50] [--all] [--dump FILE]
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
jira assets attr-create <type_id> <name> [--type text] # create attribute
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
  http.py         api_get/post/put/delete + APIError, retry with backoff on 429
  output.py       emit() with text/JSON modes, emit_error() to stderr
  confluence.py   Confluence CLI — API v2, ADF format, parallel sync
  adf.py          ADF utilities — section/extension ops, node builders, md conversion
  hints.py        Embedded hints for AI agents on ADF and macros
  jira.py         Jira CLI entry point — nested subparsers routing to:
  jira_issues.py  Issue CRUD — API v3, ADF for descriptions/comments
  jira_assets.py  Assets CRUD — Assets API v1, auto-discovers workspaceId
```

### CLI wiring pattern

All CLIs use **argparse with nested subparsers**. Each subcommand sets `p.set_defaults(func=cmd_X)`, then `main()` calls `args.func(args)`. The `--json` flag is global and toggles output mode via `set_json_mode()`. Errors are `APIError` exceptions caught in `main()`.

### Dependencies

Runtime: `requests` (HTTP), `atlas-doc-parser` (ADF-to-markdown). Dev: `pytest`, `responses` (HTTP mocking), `ruff`.

## APIs

| Service | Version | Base path |
|---------|---------|-----------|
| Confluence | v2 | `/wiki/api/v2/` |
| Jira | v3 | `/rest/api/3/` |
| Jira Assets | v1 | `api.atlassian.com/jsm/assets/workspace/{id}/v1` |

## Testing

Tests use `pytest` + `responses` for HTTP mocking. No live API calls. Test files mirror source modules 1:1 (e.g. `test_confluence.py` tests `confluence.py`). Shared fixtures in `conftest.py`: `mock_session`, `base_url`, `mocked_responses`.

## Credentials

Search order (first match wins, see `config._config_search_paths`):
1. `$ATLASSIAN_CLI_CONFIG` (explicit path)
2. `./.env` (cwd)
3. `$XDG_CONFIG_HOME/atlassian-cli/config` (default `~/.config/atlassian-cli/config`)
4. `~/.atlassian-cli/config`
5. Environment variables (`ATLASSIAN_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_TOKEN`)

```
ATLASSIAN_URL=https://your-site.atlassian.net
ATLASSIAN_EMAIL=you@example.com
ATLASSIAN_TOKEN=your-api-token
```
Falls back to `CONFLUENCE_*` prefix for backward compat.
