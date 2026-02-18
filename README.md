<p align="center">
  <h1 align="center">atlassian-cli</h1>
  <p align="center">
    Fast CLI tools for Atlassian Cloud — built for AI agents, loved by humans.
  </p>
</p>

<p align="center">
  <a href="https://github.com/catapultcx/atlassian-cli/actions/workflows/ci.yml"><img src="https://github.com/catapultcx/atlassian-cli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/atlassian-cli/"><img src="https://img.shields.io/pypi/v/atlassian-cli" alt="PyPI"></a>
  <a href="https://pypi.org/project/atlassian-cli/"><img src="https://img.shields.io/pypi/pyversions/atlassian-cli" alt="Python"></a>
  <a href="https://github.com/catapultcx/atlassian-cli/blob/main/LICENSE"><img src="https://img.shields.io/github/license/catapultcx/atlassian-cli" alt="License"></a>
</p>

---

Two CLI tools — `confluence` and `jira` — that talk directly to Atlassian Cloud REST APIs. Zero bloat, one dependency (`requests`), deterministic output that AI agents parse in a single shot.

## Install

```bash
pip install atlassian-cli
```

Or from source:

```bash
pip install git+https://github.com/catapultcx/atlassian-cli.git
```

## Setup

Create a `.env` file (or export environment variables):

```bash
ATLASSIAN_URL=https://your-site.atlassian.net
ATLASSIAN_EMAIL=you@example.com
ATLASSIAN_TOKEN=your-api-token
```

Get your API token at https://id.atlassian.com/manage-profile/security/api-tokens

> Legacy `CONFLUENCE_URL` / `CONFLUENCE_EMAIL` / `CONFLUENCE_TOKEN` env vars are also supported.

## Confluence CLI

Manages Confluence pages as local JSON files in ADF (Atlassian Document Format). No markdown — ADF preserves every macro, panel, and table perfectly.

```bash
# Download a page
confluence get 9268920323

# Upload local edits back
confluence put 9268920323
confluence put 9268920323 --force          # skip version check

# Compare local vs remote
confluence diff 9268920323

# Bulk-download an entire space (parallel, version-cached)
confluence sync POL
confluence sync COMPLY --workers 20 --force

# Search local page index (instant, no API call)
confluence search "risk assessment"

# Rebuild the page index
confluence index
confluence index --space POL --space COMPLY
```

### How sync works

`sync` downloads every page in a space using parallel workers. It caches version numbers locally — subsequent syncs only fetch pages that changed. A full space of 500+ pages takes seconds.

```
pages/
  POL/
    9268920323.json          # ADF body
    9268920323.meta.json     # title, version, timestamps
  COMPLY/
    5227515611.json
    5227515611.meta.json
page-index.json              # searchable index
```

## Jira CLI

### Issues

Full CRUD on Jira issues via REST API v3.

```bash
# Get issue details
jira issue get ISMS-42

# Create issues
jira issue create PROJ Task "Fix the login bug"
jira issue create PROJ Story "User auth" --description "As a user..." --labels security urgent
jira issue create PROJ Sub-task "Write tests" --parent PROJ-100

# Update fields
jira issue update ISMS-42 --summary "New title"
jira issue update ISMS-42 --labels risk compliance
jira issue update ISMS-42 --fields '{"priority": {"name": "High"}}'

# Delete
jira issue delete ISMS-42

# Search with JQL
jira issue search "project = ISMS AND status = Open"
jira issue search "assignee = currentUser() ORDER BY updated DESC" --max 20

# Transitions
jira issue transition ISMS-42 "In Progress"
jira issue transition ISMS-42 Done

# Comments
jira issue comment ISMS-42 "Fixed in v2.1"
jira issue comments ISMS-42
```

### Assets (JSM)

CRUD for Jira Service Management Assets via the Assets REST API v1.

```bash
# Browse schemas and types
jira assets schemas
jira assets schema 1
jira assets types 1
jira assets type 5
jira assets attrs 5

# Search with AQL
jira assets search "objectType = Server"

# CRUD objects
jira assets get 123
jira assets create 5 Name=srv01 IP=10.0.0.1
jira assets update 123 Name=srv02
jira assets delete 123

# Create new object types
jira assets type-create 1 "Network Device" --description "Switches and routers"
```

## `--json` flag

Both CLIs accept a global `--json` flag that switches all output to machine-readable JSON. Perfect for piping into `jq` or parsing from code.

```bash
# Text mode (default)
$ confluence get 9268920323
OK Artificial Intelligence Policy (v12) -> pages/POL/9268920323.json

# JSON mode
$ confluence --json get 9268920323
{"status":"ok","message":"Artificial Intelligence Policy (v12) -> pages/POL/9268920323.json"}
```

## Output format

All commands emit status-prefixed lines for easy parsing:

| Prefix | Meaning |
|--------|---------|
| `OK`   | Success |
| `GET`  | Page downloaded |
| `SKIP` | Already up-to-date |
| `ERR`  | Error |
| `DONE` | Batch complete |

## Architecture

```
src/atlassian_cli/
  config.py       Shared auth, .env parsing, session factory
  http.py         API helpers: get/post/put/delete + error handling
  output.py       Text & JSON output formatting
  confluence.py   Confluence CLI (v2 API, ADF)
  jira.py         Jira CLI entry point (subparsers)
  jira_issues.py  Jira issue commands (v3 API)
  jira_assets.py  Jira Assets commands (Assets v1 API)
```

**APIs used:**
- Confluence Cloud REST API v2 (`/wiki/api/v2/`)
- Jira Cloud REST API v3 (`/rest/api/3/`)
- Jira Assets REST API v1 (`api.atlassian.com/jsm/assets/workspace/{id}/v1`)

## Development

```bash
git clone https://github.com/catapultcx/atlassian-cli.git
cd atlassian-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## License

MIT
