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


def cmd_search(args):
    session, base = setup()
    data = api_post(session, base, f'{V3}/search/jql', {
        'jql': args.jql,
        'maxResults': args.max,
        'fields': args.fields.split(','),
    })
    issues = data.get('issues', [])
    for issue in issues:
        f = issue.get('fields', {})
        status = f.get('status', {}).get('name', '?')
        summary = f.get('summary', '')
        print(f'{issue["key"]} [{status}] {summary}')
    emit('DONE', f'{len(issues)} issues found')


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
