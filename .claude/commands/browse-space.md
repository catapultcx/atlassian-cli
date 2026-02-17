# Browse a Confluence space

Download and explore all pages in a Confluence space.

## Instructions

You are exploring a Confluence space. Use the following workflow:

### 1. Sync the space

```bash
confluence sync $ARGUMENTS --dir pages
```

This downloads all pages in the space as ADF JSON files with metadata. Uses 10 parallel workers by default.

### 2. Search for pages

```bash
confluence search "search term"
```

This searches the local page-index.json. If the index doesn't exist or is stale:

```bash
confluence index --space POL --space COMPLY
```

### 3. Read a specific page

```python
import json
from atlassian_cli.adf import adf_to_markdown

with open('pages/<SPACE>/<page_id>.json') as f:
    doc = json.load(f)
print(adf_to_markdown(doc['content']))
```

Or get the latest version from the server:

```bash
confluence get <page_id>
```

### 4. Explore page structure

```python
import json
from atlassian_cli.adf import find_sections, find_extensions

with open('pages/<SPACE>/<page_id>.json') as f:
    doc = json.load(f)

for e in find_extensions(doc['content']):
    print(f"Extension: {e['key']} - {e['title']}")

for s in find_sections(doc['content']):
    print(f"{'  ' * (s['level']-1)}H{s['level']} {s['heading']}")
```

### Tips

- Synced pages are cached — only re-downloads if remote version is newer
- Use `--force` to re-download everything
- Metadata files (`.meta.json`) contain page ID, title, version, space, and parent ID
- Use `--dir` to specify a different output directory
