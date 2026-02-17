# Claude Atlassian CLI

Fast CLI tools for Atlassian Cloud (Confluence + Jira) via REST API v2.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in credentials
```

## Confluence CLI (`conflu.py`)

All commands work with ADF (Atlassian Document Format). No markdown.

```bash
# Download a single page
python3 conflu.py get <page_id>

# Upload local edits back
python3 conflu.py put <page_id>
python3 conflu.py put <page_id> --force   # skip version check

# Compare local vs remote
python3 conflu.py diff <page_id>

# Bulk-download a space (parallel, version-cached)
python3 conflu.py sync POL
python3 conflu.py sync COMPLY --workers 20 --force

# Search local index (no API call)
python3 conflu.py search "risk"

# Rebuild page index from API
python3 conflu.py index
python3 conflu.py index --space POL --space COMPLY
```

### File layout

```
pages/
  POL/
    9268920323.json        # ADF body
    9268920323.meta.json   # Metadata (version, title, etc.)
  COMPLY/
    5227515611.json
    5227515611.meta.json
page-index.json            # Search index
```

### Output format

All commands use status prefixes for programmatic parsing:
- `OK` — success
- `GET` — page downloaded
- `SKIP` — page already up-to-date
- `ERR` — error
- `DONE` — batch operation complete

## Architecture

- `atlassian_config.py` — shared auth/config (used by all CLI tools)
- `conflu.py` — Confluence CLI
- Future: `jira.py` — Jira CLI (same shared config)
