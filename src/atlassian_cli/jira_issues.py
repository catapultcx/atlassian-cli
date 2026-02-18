"""Jira Cloud issue commands — REST API v3."""

import json
import sys

from atlassian_cli.config import setup
from atlassian_cli.http import APIError, api_delete, api_get, api_post
from atlassian_cli.output import emit, emit_error

V3 = '/rest/api/3'


def _extract_text(adf_body):
    """Recursively extract plain text from an ADF body."""
    def extract(node):
        if node.get('type') == 'text':
            return [node.get('text', '')]
        parts = []
        for child in node.get('content', []):
            parts.extend(extract(child))
        return parts
    return ' '.join(extract(adf_body))


def _text_adf(text):
    """Wrap plain text in minimal ADF document."""
    return {
        'type': 'doc', 'version': 1,
        'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}],
    }


def cmd_get(args):
    session, base = setup()
    data = api_get(session, base, f'{V3}/issue/{args.key}')
    fields = data.get('fields', {})
    status = fields.get('status', {}).get('name', '?')
    summary = fields.get('summary', '')
    emit('OK', f'{data["key"]} [{status}] {summary}', data={'key': data['key'], 'id': data['id']})


def cmd_create(args):
    session, base = setup()
    fields = {
        'project': {'key': args.project},
        'issuetype': {'name': args.type},
        'summary': args.summary,
    }
    if args.description:
        fields['description'] = _text_adf(args.description)
    if args.labels:
        fields['labels'] = args.labels
    if args.assignee:
        fields['assignee'] = {'accountId': args.assignee}
    if args.parent:
        fields['parent'] = {'key': args.parent}

    result = api_post(session, base, f'{V3}/issue', {'fields': fields})
    emit('OK', f'Created {result["key"]}', data=result)


def cmd_update(args):
    session, base = setup()
    fields = {}
    if args.summary:
        fields['summary'] = args.summary
    if args.description:
        fields['description'] = _text_adf(args.description)
    if args.labels is not None:
        fields['labels'] = args.labels
    if args.assignee:
        fields['assignee'] = {'accountId': args.assignee}
    if args.fields:
        fields.update(json.loads(args.fields))

    if not fields:
        emit_error('No fields to update')
        sys.exit(1)

    # Jira PUT /issue returns 204 No Content on success
    resp = session.put(f'{base}{V3}/issue/{args.key}', json={'fields': fields})
    if not resp.ok:
        raise APIError(resp.status_code, resp.text)
    emit('OK', f'Updated {args.key}')


def cmd_delete(args):
    session, base = setup()
    api_delete(session, base, f'{V3}/issue/{args.key}')
    emit('OK', f'Deleted {args.key}')


def _search_page(session, base, jql, max_results, fields, next_page_token=None):
    """Execute a single search/jql request, return (issues, nextPageToken)."""
    body = {'jql': jql, 'maxResults': max_results, 'fields': fields}
    if next_page_token:
        body['nextPageToken'] = next_page_token
    data = api_post(session, base, f'{V3}/search/jql', body)
    return data.get('issues', []), data.get('nextPageToken')


def cmd_search(args):
    session, base = setup()
    fields = args.fields.split(',')
    all_issues = []
    token = None

    while True:
        batch_size = min(args.max - len(all_issues), 100) if not args.all else 100
        if batch_size <= 0:
            break
        issues, token = _search_page(session, base, args.jql, batch_size,
                                     fields, token)
        all_issues.extend(issues)
        if not token or not issues:
            break
        if not args.all and len(all_issues) >= args.max:
            break

    for issue in all_issues:
        f = issue.get('fields', {})
        status = f.get('status', {}).get('name', '?')
        summary = f.get('summary', '')
        assignee = f.get('assignee', {})
        assignee_name = assignee.get('displayName', '') if assignee else ''
        extra = f'  ({assignee_name})' if assignee_name else ''
        print(f'{issue["key"]} [{status}] {summary}{extra}')

    if args.dump:
        with open(args.dump, 'w') as fh:
            json.dump({'total': len(all_issues), 'issues': all_issues}, fh, indent=2)
        print(f'Saved {len(all_issues)} issues to {args.dump}')

    emit('DONE', f'{len(all_issues)} issues found',
         data={'total': len(all_issues), 'issues': all_issues})


def cmd_transition(args):
    session, base = setup()
    data = api_get(session, base, f'{V3}/issue/{args.key}/transitions')
    transitions = data.get('transitions', [])

    target = None
    for t in transitions:
        if (t['name'].lower() == args.status.lower()
                or t.get('to', {}).get('name', '').lower() == args.status.lower()):
            target = t
            break

    if not target:
        available = ', '.join(t['name'] for t in transitions)
        emit_error(f'No transition to "{args.status}". Available: {available}')
        sys.exit(1)

    api_post(session, base, f'{V3}/issue/{args.key}/transitions',
             {'transition': {'id': target['id']}})
    emit('OK', f'{args.key} -> {target["to"]["name"]}')


def cmd_comment(args):
    session, base = setup()
    api_post(session, base, f'{V3}/issue/{args.key}/comment',
             {'body': _text_adf(args.body)})
    emit('OK', f'Comment added to {args.key}')


def cmd_comments(args):
    session, base = setup()
    data = api_get(session, base, f'{V3}/issue/{args.key}/comment')
    comments = data.get('comments', [])
    for c in comments:
        author = c.get('author', {}).get('displayName', '?')
        date = c.get('created', '')[:16]
        text = _extract_text(c.get('body', {}))[:100]
        print(f'{author} ({date}): {text}')
    emit('DONE', f'{len(comments)} comments')
