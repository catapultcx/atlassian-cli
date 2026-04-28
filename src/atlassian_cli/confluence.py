#!/usr/bin/env python3
"""Confluence Cloud CLI — fast ADF page management via REST API v2.

Commands:
    get      Download a page (ADF + metadata)
    put      Upload local ADF to Confluence
    diff     Compare local vs remote ADF
    sync     Bulk-download all pages in a space
    delete   Delete a page
    search   Search local page index
    index    Rebuild page-index.json from API
    comments List inline and footer comments on a page
    comment  Reply to a comment
    resolve  Resolve an inline comment
"""

import argparse
import difflib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from atlassian_cli.config import setup
from atlassian_cli.http import APIError, _retry, api_delete, api_get, api_post, api_put
from atlassian_cli.output import emit, emit_error, emit_json, is_json_mode, set_json_mode

V1 = '/wiki/rest/api'
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


def list_pages(session, base, space_id, statuses=('current',)):
    """Cursor-paginated listing of pages in a space, filtered by status.

    The V2 default returns *all* statuses (current, archived, draft, deleted)
    which is rarely what callers want. We default to current-only and let the
    caller widen the filter if needed."""
    pages = []
    status_q = '&'.join(f'status={s}' for s in statuses)
    url = f'{base}{V2}/spaces/{space_id}/pages?limit=250&sort=id&{status_q}'
    while url:
        resp = _retry(session.get, url)
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


def cmd_create(args):
    session, base = setup()
    space = get_space(session, base, key=args.space_key)
    space_id = space['id']

    body_payload = {}
    if args.file:
        with open(args.file) as f:
            adf = json.load(f)
        body_payload = {
            'representation': 'atlas_doc_format',
            'value': json.dumps(adf),
        }
    elif args.body:
        body_payload = {
            'representation': 'atlas_doc_format',
            'value': json.dumps({
                'type': 'doc', 'version': 1,
                'content': [{'type': 'paragraph',
                             'content': [{'type': 'text', 'text': args.body}]}],
            }),
        }

    payload = {
        'spaceId': space_id,
        'status': 'current',
        'title': args.title,
    }
    if body_payload:
        payload['body'] = body_payload
    if args.parent:
        payload['parentId'] = str(args.parent)

    result = api_post(session, base, f'{V2}/pages', payload)
    page_id = result['id']

    # Save locally
    full_page = get_page(session, base, page_id)
    space_key = space.get('key', args.space_key)
    save_page(full_page, space_key, args.dir)

    emit('OK', f'Created {result.get("title", args.title)} ({page_id})')


def _modify_page_metadata(session, base, page_id, *,
                          new_title=None, new_parent_id=None, message=None):
    """Update a page's title and/or parentId without touching the body.

    Confluence has no dedicated 'move' or 'rename' endpoint — both go through
    PUT /pages/{id}, which requires the full body and a bumped version. Here
    we fetch the current state and round-trip it with the requested changes.
    """
    remote = get_page(session, base, page_id)
    current_title = remote.get('title', '')
    title = new_title if new_title is not None else current_title
    body_value = remote.get('body', {}).get('atlas_doc_format', {}).get('value')
    if body_value is None:
        body_value = {'type': 'doc', 'version': 1, 'content': []}
    body_payload = {
        'representation': 'atlas_doc_format',
        'value': json.dumps(body_value) if not isinstance(body_value, str) else body_value,
    }
    new_version = _ver(remote) + 1
    payload = {
        'id': str(page_id),
        'status': 'current',
        'title': title,
        'body': body_payload,
        'version': {'number': new_version, 'message': message or 'Metadata updated'},
    }
    if new_parent_id is not None:
        payload['parentId'] = str(new_parent_id)
    api_put(session, base, f'{V2}/pages/{page_id}', payload)
    return title, new_version


def cmd_move(args):
    session, base = setup()
    new_title, new_version = _modify_page_metadata(
        session, base, args.page_id,
        new_parent_id=args.parent_id,
        message=getattr(args, 'message', None) or f'Moved under parent {args.parent_id}',
    )
    emit('OK', f'Moved {args.page_id} ({new_title}) -> parent {args.parent_id} (v{new_version})')


def cmd_rename(args):
    session, base = setup()
    new_title, new_version = _modify_page_metadata(
        session, base, args.page_id,
        new_title=args.title,
        message=getattr(args, 'message', None) or f'Renamed to {args.title!r}',
    )
    emit('OK', f'Renamed {args.page_id} -> {new_title!r} (v{new_version})')


def cmd_delete(args):
    session, base = setup()
    page = get_page(session, base, args.page_id)
    title = page.get('title', args.page_id)
    api_delete(session, base, f'{V2}/pages/{args.page_id}')
    emit('OK', f'Deleted {title} ({args.page_id})')


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
            'message': getattr(args, 'message', None) or 'Updated via confluence CLI',
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

    statuses = ('current', 'archived') if args.include_archived else ('current',)
    for space_key in spaces:
        space = get_space(session, base, key=space_key)
        space_id = space['id']
        print(f'Indexing {space_key}…', file=sys.stderr)
        pages = list_pages(session, base, space_id, statuses=statuses)

        index[space_key] = []
        for page in pages:
            index[space_key].append({
                'id': page['id'],
                'title': page.get('title', ''),
                'parentId': page.get('parentId', ''),
                'version': _ver(page),
                'updatedAt': _ver_ts(page),
                'status': page.get('status', 'current'),
            })
        print(f'  {space_key}: {len(pages)} pages', file=sys.stderr)

    with open(args.output, 'w') as f:
        json.dump(index, f, indent=2)

    total = sum(len(v) for v in index.values())
    emit('DONE', f'{total} pages indexed -> {args.output}')


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def _adf_to_text(node):
    """Recursively extract plain text from an ADF node."""
    if isinstance(node, str):
        try:
            node = json.loads(node)
        except (json.JSONDecodeError, TypeError):
            return node
    if isinstance(node, dict):
        if node.get('type') == 'text':
            return node.get('text', '')
        if node.get('type') == 'hardBreak':
            return '\n'
        parts = []
        for child in node.get('content', []):
            parts.append(_adf_to_text(child))
        return ''.join(parts)
    if isinstance(node, list):
        return ''.join(_adf_to_text(item) for item in node)
    return ''


def _make_adf_body(text):
    """Create a simple ADF document from plain text."""
    return {
        'type': 'doc',
        'version': 1,
        'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}
        ],
    }


def list_comments(session, base, page_id, comment_type='inline'):
    """Fetch all comments on a page. comment_type: 'inline' or 'footer'."""
    endpoint = 'inline-comments' if comment_type == 'inline' else 'footer-comments'
    comments = []
    url = f'{base}{V2}/pages/{page_id}/{endpoint}?body-format=atlas_doc_format'
    while url:
        resp = _retry(session.get, url)
        resp.raise_for_status()
        data = resp.json()
        comments.extend(data.get('results', []))
        next_link = data.get('_links', {}).get('next')
        url = f'{base}{next_link}' if next_link and next_link.startswith('/') else next_link
    return comments


def list_comment_replies(session, base, comment_id, comment_type='inline'):
    """Fetch child comments (replies) for a given comment."""
    prefix = 'inline-comments' if comment_type == 'inline' else 'footer-comments'
    replies = []
    url = f'{base}{V2}/{prefix}/{comment_id}/children?body-format=atlas_doc_format'
    while url:
        resp = _retry(session.get, url)
        if not resp.ok:
            return []
        data = resp.json()
        replies.extend(data.get('results', []))
        next_link = data.get('_links', {}).get('next')
        url = f'{base}{next_link}' if next_link and next_link.startswith('/') else next_link
    return replies


def reply_to_comment(session, base, comment_id, body_text, comment_type='inline'):
    """Post a reply to an existing comment via v2 API."""
    endpoint = 'inline-comments' if comment_type == 'inline' else 'footer-comments'
    payload = {
        'parentCommentId': str(comment_id),
        'body': {
            'representation': 'atlas_doc_format',
            'value': json.dumps(_make_adf_body(body_text)),
        },
    }
    return api_post(session, base, f'{V2}/{endpoint}', payload)


def get_inline_comment(session, base, comment_id):
    """Fetch a single inline comment with body."""
    return api_get(session, base, f'{V2}/inline-comments/{comment_id}',
                   **{'body-format': 'atlas_doc_format'})


def resolve_comment(session, base, comment_id, resolved=True):
    """Resolve or reopen an inline comment.

    Uses PUT /inline-comments/{id} with the 'resolved' boolean field.
    Requires the current body and an incremented version number.
    """
    comment = get_inline_comment(session, base, comment_id)
    current_ver = comment.get('version', {}).get('number', 0)
    body_raw = comment.get('body', {}).get('atlas_doc_format', {}).get('value', '{}')

    payload = {
        'version': {'number': current_ver + 1},
        'body': {
            'representation': 'atlas_doc_format',
            'value': body_raw if isinstance(body_raw, str) else json.dumps(body_raw),
        },
        'resolved': resolved,
    }
    return api_put(session, base, f'{V2}/inline-comments/{comment_id}', payload)


V1 = '/wiki/rest/api'

_user_cache = {}


def _resolve_user(session, base, account_id):
    """Look up display name for an Atlassian account ID. Cached."""
    if not account_id:
        return 'Unknown'
    if account_id in _user_cache:
        return _user_cache[account_id]
    try:
        data = api_get(session, base, f'{V1}/user', accountId=account_id)
        name = data.get('displayName', account_id)
    except APIError:
        name = account_id
    _user_cache[account_id] = name
    return name


def cmd_comments(args):
    session, base = setup()
    page_id = args.page_id

    inline = list_comments(session, base, page_id, 'inline')
    footer = list_comments(session, base, page_id, 'footer')

    all_comments = []

    for c in inline:
        body_raw = c.get('body', {}).get('atlas_doc_format', {}).get('value', '{}')
        text = _adf_to_text(body_raw).strip()
        props = c.get('properties', {})
        selection = props.get('inline-original-selection', '')
        status = c.get('resolutionStatus', 'open')

        if args.open_only and status != 'open':
            continue

        author_id = c.get('version', {}).get('authorId', '')
        author = _resolve_user(session, base, author_id)

        entry = {
            'id': c['id'],
            'type': 'inline',
            'status': status,
            'author': author,
            'selection': selection,
            'text': text,
            'created': c.get('version', {}).get('createdAt', ''),
        }

        # Fetch replies
        replies = list_comment_replies(session, base, c['id'], 'inline')
        entry['replies'] = []
        for r in replies:
            r_body = r.get('body', {}).get('atlas_doc_format', {}).get('value', '{}')
            r_author_id = r.get('version', {}).get('authorId', '')
            entry['replies'].append({
                'id': r['id'],
                'author': _resolve_user(session, base, r_author_id),
                'text': _adf_to_text(r_body).strip(),
                'created': r.get('version', {}).get('createdAt', ''),
            })

        all_comments.append(entry)

    for c in footer:
        body_raw = c.get('body', {}).get('atlas_doc_format', {}).get('value', '{}')
        text = _adf_to_text(body_raw).strip()
        status = c.get('resolutionStatus', 'open')

        if args.open_only and status != 'open':
            continue

        author_id = c.get('version', {}).get('authorId', '')
        author = _resolve_user(session, base, author_id)

        entry = {
            'id': c['id'],
            'type': 'footer',
            'status': status,
            'author': author,
            'selection': '',
            'text': text,
            'created': c.get('version', {}).get('createdAt', ''),
        }

        replies = list_comment_replies(session, base, c['id'], 'footer')
        entry['replies'] = []
        for r in replies:
            r_body = r.get('body', {}).get('atlas_doc_format', {}).get('value', '{}')
            r_author_id = r.get('version', {}).get('authorId', '')
            entry['replies'].append({
                'id': r['id'],
                'author': _resolve_user(session, base, r_author_id),
                'text': _adf_to_text(r_body).strip(),
                'created': r.get('version', {}).get('createdAt', ''),
            })

        all_comments.append(entry)

    if args.json_output:
        print(json.dumps(all_comments, indent=2))
        return

    if not all_comments:
        emit('OK', 'No comments found')
        return

    for c in all_comments:
        status_marker = '\u2713' if c['status'] == 'resolved' else '\u25cb'
        type_label = c['type'].upper()
        print(f'{status_marker} [{type_label}] #{c["id"]} ({c["status"]}) — {c["author"]}')
        if c['selection']:
            sel = c['selection'][:100]
            print(f'  On: "{sel}{"..." if len(c["selection"]) > 100 else ""}"')
        print(f'  {c["text"]}')
        for r in c['replies']:
            print(f'    \u2514\u2500 {r["author"]}: {r["text"]}')
        print()

    total = len(all_comments)
    open_count = sum(1 for c in all_comments if c['status'] == 'open')
    emit('DONE', f'{total} comments ({open_count} open)')


def cmd_comment(args):
    session, base = setup()
    comment_type = 'footer' if args.footer else 'inline'
    result = reply_to_comment(session, base, args.comment_id, args.body, comment_type)
    reply_id = result.get('id', '?')
    emit('OK', f'Replied to comment #{args.comment_id} (reply #{reply_id})')


def cmd_resolve(args):
    session, base = setup()
    resolved = not args.reopen
    resolve_comment(session, base, args.comment_id, resolved)
    action = 'Resolved' if resolved else 'Reopened'
    emit('OK', f'{action} comment #{args.comment_id}')


# ---------------------------------------------------------------------------
# hints
# ---------------------------------------------------------------------------

def cmd_hints(args):
    """Print hints for AI agents (or humans) working with ADF."""
    from atlassian_cli.hints import format_hints, get_hints

    if args.json_output:
        from atlassian_cli.hints import get_hint
        if args.topic:
            data = get_hint(args.topic)
            if data is None:
                emit_error(f'Unknown topic: {args.topic}. Available: {", ".join(get_hints().keys())}')
                return
        else:
            data = get_hints()
        print(json.dumps(data, indent=2))
    else:
        if args.topic and args.topic not in get_hints():
            emit_error(f'Unknown topic: {args.topic}. Available: {", ".join(get_hints().keys())}')
            return
        print(format_hints(args.topic))


# ---------------------------------------------------------------------------
# Page version changes
# ---------------------------------------------------------------------------

def cmd_changes(args):
    """Show what changed in the latest version of a page."""
    session, base = setup()
    page_id = args.page_id

    current = api_get(session, base, f'{V2}/pages/{page_id}?body-format=atlas_doc_format&include-version=true')
    cur_ver = current['version']['number']
    title = current['title']
    author_id = current['version'].get('authorId', '?')
    created = current['version'].get('createdAt', '?')[:16]

    prev_ver = args.version or cur_ver - 1
    if prev_ver < 1:
        emit_error('Only one version exists — nothing to compare')
        sys.exit(1)

    # v1 API required for historical version bodies
    prev_resp = session.get(
        f'{base}{V1}/content/{page_id}',
        params={'status': 'historical', 'version': prev_ver, 'expand': 'body.atlas_doc_format'},
    )
    if not prev_resp.ok:
        raise APIError(prev_resp.status_code, prev_resp.text)

    from atlassian_cli.adf import adf_to_markdown
    cur_body = json.loads(current['body']['atlas_doc_format']['value'])
    prev_body = json.loads(prev_resp.json()['body']['atlas_doc_format']['value'])

    cur_md = adf_to_markdown(cur_body).splitlines()
    prev_md = adf_to_markdown(prev_body).splitlines()

    diff_lines = list(difflib.unified_diff(
        prev_md, cur_md, fromfile=f'v{prev_ver}', tofile=f'v{cur_ver}', lineterm='',
    ))

    if not is_json_mode():
        print(f'{title} — v{prev_ver} → v{cur_ver} (by {author_id[:20]} at {created})')
        print()
        if diff_lines:
            print('\n'.join(diff_lines))
        else:
            print('No content changes between versions')
    else:
        emit_json({
            'page_id': page_id, 'title': title,
            'from_version': prev_ver, 'to_version': cur_ver,
            'author': author_id, 'date': created,
            'diff': '\n'.join(diff_lines) if diff_lines else None,
        })


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

def _get_current_user_id(session, base):
    data = api_get(session, base, f'{V1}/user/current')
    return data['accountId']


def _get_approval_property(session, base, page_id):
    try:
        return api_get(session, base, f'{V1}/content/{page_id}/property/approvals')
    except APIError:
        return None


def cmd_approvals(args):
    """List pages pending your approval (CQL + expand, client-side filter)."""
    session, base = setup()
    my_id = _get_current_user_id(session, base)

    cql = 'type=page AND content.property[approvals].allDone=0'
    if args.spaces:
        space_clause = ' OR '.join(f'space.key={s}' for s in args.spaces)
        cql += f' AND ({space_clause})'

    # Single CQL call with expanded approval properties — client-side filter by user.
    # CQL can't query into arrays, so we filter the 'pending' list in Python.
    pending = []
    seen = set()
    start = 0
    while True:
        resp = session.get(f'{base}{V1}/search', params={
            'cql': cql, 'limit': 100, 'start': start, 'excerpt': 'none',
            'expand': 'content.metadata.properties.approvals,content.space',
        })
        if not resp.ok:
            raise APIError(resp.status_code, resp.text)
        data = resp.json()
        results = data.get('results', [])
        if not results:
            break

        for r in results:
            c = r.get('content', {})
            page_id = c.get('id')
            if not page_id or page_id in seen:
                continue
            seen.add(page_id)
            value = c.get('metadata', {}).get('properties', {}).get('approvals', {}).get('value', {})
            if my_id in value.get('pending', []):
                pending.append({
                    'page_id': page_id,
                    'title': c.get('title', '?'),
                    'space': c.get('space', {}).get('key', '?'),
                    'status': value.get('name', {}).get('value', '?'),
                })

        total = data.get('totalSize', 0)
        start += len(results)
        if start >= total:
            break

    if is_json_mode():
        emit_json(pending)
    elif not pending:
        emit('OK', 'No pending approvals')
    else:
        for p in pending:
            print(f'{p["page_id"]} [{p["space"]}] {p["title"]}  ({p["status"]})')
        emit('DONE', f'{len(pending)} pending approval(s)')


def cmd_approve(args):
    """Approve or reject a page."""
    import time
    session, base = setup()
    my_id = _get_current_user_id(session, base)
    page_id = args.page_id
    reject = getattr(args, 'reject', False)

    prop = _get_approval_property(session, base, page_id)
    if not prop:
        emit_error(f'No approval property on page {page_id}')
        sys.exit(1)

    value = prop['value']
    version = prop['version']['number']

    if my_id not in value.get('pending', []):
        emit_error(f'You are not a pending approver on page {page_id}')
        sys.exit(1)

    now = int(time.time() * 1000)
    status_code = 2 if reject else 1  # 0=pending, 1=approved, 2=rejected
    target_list = 'rejected' if reject else 'completed'

    for a in value['approvers']:
        if a['approverid'] == my_id:
            a['status'] = status_code
            a['date'] = now

    value['pending'] = [p for p in value['pending'] if p != my_id]
    value[target_list].append(my_id)

    total = len(value['approvers'])
    done = len(value['completed'])
    rejected = len(value['rejected'])

    if value['pending']:
        label = f'Pending ({done}/{total})'
        tooltip = 'There are pending approvals.'
        icon = '0'
    elif rejected:
        label = f'Rejected ({rejected}/{total})'
        tooltip = 'Approval was rejected.'
        icon = '2'
    else:
        label = f'Approved ({done}/{total})'
        tooltip = 'All approvals are complete.'
        icon = '1'

    value['allDone'] = '0' if value['pending'] else '1'
    value['name']['value'] = label
    value['tooltip']['value'] = tooltip
    value['icon']['url'] = f'/approvalmacro/images/{icon}.svg'

    api_put(session, base, f'{V1}/content/{page_id}/property/approvals', {
        'key': 'approvals',
        'value': value,
        'version': {'number': version + 1},
    })

    action = 'Rejected' if reject else 'Approved'
    emit('OK', f'{action} page {page_id} ({label})')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    from atlassian_cli.update_check import check_for_update
    check_for_update()

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

    p = sub.add_parser('create', help='Create a new page')
    p.add_argument('space_key', help='Space key (e.g. POL, COMPLY)')
    p.add_argument('title', help='Page title')
    p.add_argument('--body', help='Plain text body')
    p.add_argument('--file', '-f', help='ADF JSON file for page body')
    p.add_argument('--parent', help='Parent page ID')
    p.add_argument('--dir', default='pages', help='Pages directory (default: pages)')
    p.set_defaults(func=cmd_create)

    p = sub.add_parser('delete', help='Delete a page')
    p.add_argument('page_id', help='Confluence page ID')
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser('move', help='Move a page to a new parent (preserves body)')
    p.add_argument('page_id', help='Confluence page ID to move')
    p.add_argument('parent_id', help='New parent page ID')
    p.add_argument('--message', '-m', help='Version message')
    p.set_defaults(func=cmd_move)

    p = sub.add_parser('rename', help='Rename a page (preserves body and parent)')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('title', help='New page title')
    p.add_argument('--message', '-m', help='Version message')
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser('put', help='Upload local ADF to Confluence')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('--dir', default='pages', help='Pages directory (default: pages)')
    p.add_argument('--force', action='store_true', help='Skip version conflict check')
    p.add_argument('--message', '-m', help='Version message (shown in page history)')
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
    p.add_argument('--include-archived', action='store_true',
                   help='Also include archived pages (default is current only)')
    p.set_defaults(func=cmd_index)

    p = sub.add_parser('comments', help='List comments on a page')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('--open', action='store_true', dest='open_only', help='Show only open/unresolved comments')
    p.set_defaults(func=cmd_comments)

    p = sub.add_parser('comment', help='Reply to a comment')
    p.add_argument('comment_id', help='Comment ID to reply to')
    p.add_argument('body', help='Reply text')
    p.add_argument('--footer', action='store_true', help='Reply to a footer comment (default: inline)')
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser('resolve', help='Resolve or reopen an inline comment')
    p.add_argument('comment_id', help='Comment ID to resolve')
    p.add_argument('--reopen', action='store_true', help='Reopen instead of resolve')
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser('hints', help='Show hints for working with ADF and Confluence macros')
    p.add_argument('topic', nargs='?', help='Topic: macros, sections, editing, adf_basics (default: all)')
    p.set_defaults(func=cmd_hints)

    p = sub.add_parser('changes', help='Show what changed in the latest version of a page')
    p.add_argument('page_id', help='Confluence page ID')
    p.add_argument('--version', type=int, help='Compare against this version (default: previous)')
    p.set_defaults(func=cmd_changes)

    p = sub.add_parser('approvals', help='List pages pending your approval')
    p.add_argument('--spaces', nargs='*', help='Space keys to search (default: COMPLY POL ICOMB)')
    p.set_defaults(func=cmd_approvals)

    p = sub.add_parser('approve', help='Approve a page')
    p.add_argument('page_id', help='Confluence page ID')
    p.set_defaults(func=cmd_approve, reject=False)

    p = sub.add_parser('reject', help='Reject a page approval')
    p.add_argument('page_id', help='Confluence page ID')
    p.set_defaults(func=cmd_approve, reject=True)

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
