# Edit a Confluence page

Edit a Confluence page safely using section-level and extension-level ADF operations.

## Instructions

You are editing a Confluence page. Follow this workflow exactly:

### 1. Download the page

```bash
confluence get $ARGUMENTS
```

This saves the ADF content and metadata locally. Note the version number.

### 2. Inspect the page

Use Python to understand the page structure:

```python
import json
from atlassian_cli.adf import adf_to_markdown, find_sections, find_extensions

with open('pages/<SPACE>/<page_id>.json') as f:
    doc = json.load(f)
content = doc['content']

# Show extensions (macros like panelbox)
for e in find_extensions(content):
    print(f"[{e['index']}] {e['key']}: {e['title']}")

# Show sections (heading-based)
for s in find_sections(content):
    print(f"L{s['level']} [{s['start']}:{s['end']}] {s['heading']}")

# Full markdown preview
print(adf_to_markdown(content))
```

### 3. Make targeted edits

Use `replace_section()`, `replace_extension()`, `insert_after()`, or `extract_section()`. NEVER rewrite the entire page — only modify the specific section or extension content that needs changing.

For extensions (macros like panelbox): only replace the `content` array — the wrapper with attrs, parameters, macroId, and localId must be preserved exactly.

### 4. Preview and save

```python
# Preview the changed area
print(adf_to_markdown(updated_content))

# Save locally
doc['content'] = updated_content
with open('pages/<SPACE>/<page_id>.json', 'w') as f:
    json.dump(doc, f, indent=2)
```

### 5. Upload

```bash
confluence put <page_id>
```

### Rules

- Always get the page first to have the current version
- Use section/extension operations, never rewrite the whole document
- Preserve all bodiedExtension wrappers — only modify content arrays inside
- Do not rename or restyle existing macros unless explicitly asked
- Preview with adf_to_markdown() before uploading
- If unsure about macro structure, run: `confluence hints macros`
