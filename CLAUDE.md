# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
pip install -e ".[dev]"      # install with test/lint deps
pytest                        # run tests (79 tests, <1s)
ruff check src/ tests/        # lint
```

## Commands

Two entry points: `confluence` and `jira`.

### Confluence

```bash
confluence get <page_id>                    # download page (ADF + meta)
confluence put <page_id> [--force]          # upload local edits
confluence diff <page_id>                   # compare local vs remote
confluence sync <space_key> [--workers 10]  # bulk-download space (parallel)
confluence search <query>                   # search local page-index.json
confluence index [--space POL --space COMPLY] # rebuild index from API
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

All commands accept `--json` for machine-readable output.

## Architecture

```
src/atlassian_cli/
  config.py       .env parsing, auth, session factory — setup() returns (session, base_url)
  http.py         api_get/post/put/delete + APIError exception
  output.py       emit() with text/JSON modes, emit_error() to stderr
  conflu.py       Confluence CLI — API v2, ADF format, parallel sync
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
pytest tests/test_conflu.py   # single module
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
