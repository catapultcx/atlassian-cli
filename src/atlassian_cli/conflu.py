#!/usr/bin/env python3
"""Confluence Cloud CLI — fast ADF page management via REST API v2.

Commands:
    get     Download a page (ADF + metadata)
    put     Upload local ADF to Confluence
    diff    Compare local vs remote ADF
    sync    Bulk-download all pages in a space
    search  Search local page index
    index   Rebuild page-index.json from API
"""

import argparse
import difflib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from atlassian_cli.config import setup
from atlassian_cli.http import APIError, api_get, api_put
from atlassian_cli.output import emit, emit_error, set_json_mode

V2 = '/wiki/api/v2'


# ---------------------------------------------------------------------------
# Confluence v2 methods
# ---------------------------------------------------------------------------

_space_cache = {}


def get_page(session, base, page_id):
    """Fetch a single page with ADF body."""
    data = api_get(session, base, f'{V2}/pages/{page_id}',
                   **{'body-format': 'atlas_doc_format'})
    body = data.get('body', {}).get('atlas_doc_format', {})
    if isinstance(body.get('value'), str):
        try:
            body['value'] = json.loads(body['value'])
        except json.JSONDecodeError:
            pass
    return data


def get_space(session, base, *, key=None, space_id=None):
    """Look up a space by key or ID. Results are cached."""
    if key and key in _space_cache:
        return _space_cache[key]
    if space_id and space_id in _space_cache:
        return _space_cache[space_id]

    if key:
        data = api_get(session, base, f'{V2}/spaces', keys=key)
        results = data.get('results', [])
        if not results:
            raise APIError(404, f'Space not found: {key}')
        space = results[0]
    elif space_id:
        space = api_get(session, base, f'{V2}/spaces/{space_id}')
    else:
        raise ValueError('Provide key or space_id')

    _space_cache[space.get('key', '')] = space
    _space_cache[space['id']] = space
    return space


def list_pages(session, base, space_id):
    """Cursor-paginated listing of all pages in a space."""
    pages = []
    url = f'{base}{V2}/spaces/{space_id}/pages?limit=250&sort=id'
    while url:
        resp = session.get(url)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data.get('results', []))
        next_link = data.get('_links', {}).get('next')
        if next_link:
            url = f'{base}{next_link}' if next_link.startswith('/') else next_link
        else:
            url = None
    return pages


# ---------------------------------------------------------------------------
# Local file I/O
# ---------------------------------------------------------------------------

def _ver(page):
    v = page.get('version', {})
    return v.get('number', 0) if isinstance(v, dict) else int(v or 0)


def _ver_ts(page):
    v = page.get('version', {})
    return v.get('createdAt', '') if isinstance(v, dict) else ''


def save_page(page_data, space_key, pages_dir):
    page_id = page_data['id']
    space_dir = os.path.join(pages_dir, space_key)
    os.makedirs(space_dir, exist_ok=True)

    body = page_data.get('body', {}).get('atlas_doc_format', {}).get('value', {})
    adf_path = os.path.join(space_dir, f'{page_id}.json')
    with open(adf_path, 'w') as f:
        json.dump(body, f, indent=2)

    meta = {
        'id': page_id,
        'title': page_data.get('title', ''),
        'spaceId': page_data.get('spaceId', ''),
        'spaceKey': space_key,
        'version': _ver(page_data),
        'parentId': page_data.get('parentId', ''),
        'updatedAt': _ver_ts(page_data),
    }
    meta_path = os.path.join(space_dir, f'{page_id}.meta.json')
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    return adf_path, meta_path


def _find_page_file(page_id, pages_dir, suffix):
    if not os.path.isdir(pages_dir):
        return None
    for entry in os.listdir(pages_dir):
        candidate = os.path.join(pages_dir, entry, f'{page_id}{suffix}')
        if os.path.isfile(candidate):
            return candidate
    return None


def load_meta(page_id, pages_dir):
    path = _find_page_file(page_id, pages_dir, '.meta.json')
    if not path:
        return None
    with open(path) as f:
        return json.load(f)


def load_adf(page_id, pages_dir):
    path = _find_page_file(page_id, pages_dir, '.json')
    if not path:
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_get(args):
    session, base = setup()
    page = get_page(session, base, args.page_id)
    space = get_space(session, base, space_id=page['spaceId'])
    space_key = space.get('key', str(page['spaceId']))
    adf_path, _ = save_page(page, space_key, args.dir)
    emit('OK', f'{page["title"]} (v{_ver(page)}) -> {adf_path}')


def cmd_put(args):
    session, base = setup()

    meta = load_meta(args.page_id, args.dir)
    if not meta:
        emit_error(f'No local metadata for page {args.page_id}')
        sys.exit(1)
    adf = load_adf(args.page_id, args.dir)
    if not adf:
        emit_error(f'No local ADF for page {args.page_id}')
        sys.exit(1)

    remote = get_page(session, base, args.page_id)
    remote_ver = _ver(remote)
    local_ver = meta.get('version', 0)

    if not args.force and remote_ver != local_ver:
        emit_error(f'Version conflict: local v{local_ver}, remote v{remote_ver}. Use --force to overwrite.')
        sys.exit(1)

    new_version = remote_ver + 1
    result = api_put(session, base, f'{V2}/pages/{args.page_id}', {
        'id': str(args.page_id),
        'status': 'current',
        'title': meta['title'],
        'body': {
            'representation': 'atlas_doc_format',
            'value': json.dumps(adf),
        },
        'version': {
            'number': new_version,
            'message': 'Updated via confluence CLI',
        },
    })

    meta['version'] = new_version
    meta['updatedAt'] = _ver_ts(result)
    space_key = meta.get('spaceKey', '')
    meta_path = os.path.join(args.dir, space_key, f'{args.page_id}.meta.json')
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    emit('OK', f'{meta["title"]} updated to v{new_version}')


def cmd_diff(args):
    session, base = setup()

    local_adf = load_adf(args.page_id, args.dir)
    if not local_adf:
        emit_error(f'No local ADF for page {args.page_id}')
        sys.exit(1)

    remote = get_page(session, base, args.page_id)
    remote_adf = remote.get('body', {}).get('atlas_doc_format', {}).get('value', {})

    local_lines = json.dumps(local_adf, indent=2, sort_keys=True).splitlines(keepends=True)
    remote_lines = json.dumps(remote_adf, indent=2, sort_keys=True).splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        local_lines, remote_lines,
        fromfile=f'local/{args.page_id}.json',
        tofile=f'remote/{args.page_id}',
    ))
    if diff:
        sys.stdout.writelines(diff)
    else:
        meta = load_meta(args.page_id, args.dir) or {}
        emit('OK', f'No differences — {meta.get("title", args.page_id)}')


def cmd_sync(args):
    session, base = setup()
    space = get_space(session, base, key=args.space_key)
    space_id = space['id']
    space_key = space.get('key', args.space_key)

    print(f'Listing pages in {space_key}…', file=sys.stderr)
    pages = list_pages(session, base, space_id)
    print(f'Found {len(pages)} pages', file=sys.stderr)

    to_fetch = []
    skipped = 0
    for page in pages:
        page_id = page['id']
        remote_ver = _ver(page)
        if not args.force:
            meta = load_meta(page_id, args.dir)
            if meta and meta.get('version', 0) >= remote_ver:
                skipped += 1
                continue
        to_fetch.append(page)

    if skipped:
        print(f'SKIP {skipped} pages already up-to-date', file=sys.stderr)

    if not to_fetch:
        emit('DONE', f'{space_key}: {len(pages)} pages, all up-to-date')
        return

    print(f'Fetching {len(to_fetch)} pages ({args.workers} workers)…', file=sys.stderr)

    errors = 0

    def fetch_one(page):
        nonlocal errors
        page_id = page['id']
        try:
            full_page = get_page(session, base, page_id)
            save_page(full_page, space_key, args.dir)
            return f'GET {page_id} {full_page.get("title", "")} (v{_ver(full_page)})'
        except Exception as e:
            errors += 1
            return f'ERR {page_id} {page.get("title", "")}: {e}'

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, p): p for p in to_fetch}
        for future in as_completed(futures):
            print(future.result())

    emit('DONE', f'{space_key}: {len(to_fetch)} fetched, {skipped} skipped, {errors} errors')


def cmd_search(args):
    if not os.path.isfile(args.index):
        emit_error(f'Index not found: {args.index}')
        sys.exit(1)

    with open(args.index) as f:
        index = json.load(f)

    query = args.query.lower()

    if isinstance(index, dict):
        flat = []
        for space_key, pages in index.items():
            for p in pages:
                p.setdefault('spaceKey', space_key)
                flat.append(p)
    else:
        flat = index

    results = [
        p for p in flat
        if query in p.get('title', '').lower() or query in str(p.get('id', ''))
    ]

    for p in results:
        print(f'{p["id"]} [{p.get("spaceKey", "?")}] {p.get("title", "")}')

    if not results:
        print('No results.', file=sys.stderr)


def cmd_index(args):
    session, base = setup()
    spaces = args.space if args.space else ['POL', 'COMPLY']
    index = {}

    for space_key in spaces:
        space = get_space(session, base, key=space_key)
        space_id = space['id']
        print(f'Indexing {space_key}…', file=sys.stderr)
        pages = list_pages(session, base, space_id)

        index[space_key] = []
        for page in pages:
            index[space_key].append({
                'id': page['id'],
                'title': page.get('title', ''),
                'parentId': page.get('parentId', ''),
                'version': _ver(page),
                'updatedAt': _ver_ts(page),
            })
        print(f'  {space_key}: {len(pages)} pages', file=sys.stderr)

    with open(args.output, 'w') as f:
        json.dump(index, f, indent=2)

    total = sum(len(v) for v in index.values())
    emit('DONE', f'{total} pages indexed -> {args.output}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog='confluence',
        description='Confluence Cloud CLI — fast ADF page management',
    )
    parser.add_argument('--json', action='store_true', dest='json_output',
                        help='Output as JSON for programmatic parsing')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('get', help='Download a page (ADF + metadata)')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('--dir', default='pages', help='Output directory (default: pages)')
    p.set_defaults(func=cmd_get)

    p = sub.add_parser('put', help='Upload local ADF to Confluence')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('--dir', default='pages', help='Pages directory (default: pages)')
    p.add_argument('--force', action='store_true', help='Skip version conflict check')
    p.set_defaults(func=cmd_put)

    p = sub.add_parser('diff', help='Compare local vs remote ADF')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('--dir', default='pages', help='Pages directory (default: pages)')
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser('sync', help='Bulk-download all pages in a space')
    p.add_argument('space_key', help='Space key (e.g. POL, COMPLY)')
    p.add_argument('--dir', default='pages', help='Output directory (default: pages)')
    p.add_argument('--workers', type=int, default=10, help='Parallel workers (default: 10)')
    p.add_argument('--force', action='store_true', help='Re-download all, ignore cache')
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser('search', help='Search local page index')
    p.add_argument('query', help='Search term (title or ID)')
    p.add_argument('--index', default='page-index.json', help='Index file path')
    p.set_defaults(func=cmd_search)

    p = sub.add_parser('index', help='Rebuild page-index.json from API')
    p.add_argument('--space', action='append', help='Space key(s) to index (default: POL COMPLY)')
    p.add_argument('--output', default='page-index.json', help='Output file (default: page-index.json)')
    p.set_defaults(func=cmd_index)

    args = parser.parse_args()
    if args.json_output:
        set_json_mode(True)
    try:
        args.func(args)
    except APIError as e:
        emit_error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == '__main__':
    main()
