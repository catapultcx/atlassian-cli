"""Jira Assets (JSM) commands — Assets REST API v1."""

import json
import os
import sys

from atlassian_cli.config import setup
from atlassian_cli.http import APIError, api_delete, api_get, api_post, api_put
from atlassian_cli.output import emit, emit_error, emit_json

CACHE_FILE = '.atlassian-cache.json'


def _discover(session, base):
    """Discover cloudId and workspaceId. Results cached to disk."""
    cache_path = os.path.join(os.getcwd(), CACHE_FILE)
    if os.path.isfile(cache_path):
        with open(cache_path) as f:
            cache = json.load(f)
        if cache.get('base') == base:
            return cache['cloud_id'], cache['workspace_id']

    # Step 1: cloudId
    resp = session.get(f'{base}/_edge/tenant_info')
    if not resp.ok:
        raise APIError(resp.status_code, f'Failed to get cloudId: {resp.text}')
    cloud_id = resp.json()['cloudId']

    # Step 2: workspaceId
    resp = session.get(f'{base}/rest/servicedeskapi/assets/workspace')
    if not resp.ok:
        raise APIError(resp.status_code, f'Failed to get workspaceId: {resp.text}')
    workspace_id = resp.json()['values'][0]['workspaceId']

    # Cache
    with open(cache_path, 'w') as f:
        json.dump({'base': base, 'cloud_id': cloud_id, 'workspace_id': workspace_id}, f)

    return cloud_id, workspace_id


def _assets_base(session, base):
    """Return the Assets API base URL."""
    _, workspace_id = _discover(session, base)
    return f'https://api.atlassian.com/jsm/assets/workspace/{workspace_id}/v1'


def assets_setup():
    """Return (session, site_base, assets_base_url)."""
    session, base = setup()
    ab = _assets_base(session, base)
    return session, base, ab


def resolve_schema(session, ab, name_or_id):
    """Resolve a schema name to its ID, or pass through if already numeric."""
    if name_or_id.isdigit():
        return name_or_id
    data = api_get(session, ab, '/objectschema/list')
    schemas = data.get('values', data.get('objectschemas', []))
    for s in schemas:
        if s['name'].lower() == name_or_id.lower():
            return str(s['id'])
    raise APIError(404, f'Schema not found: {name_or_id}')


def _parse_attrs(attr_list):
    """Parse key=value pairs into Assets API attribute format."""
    attrs = []
    for pair in attr_list:
        if '=' not in pair:
            emit_error(f'Invalid attribute format: {pair} (expected key=value)')
            sys.exit(1)
        key, value = pair.split('=', 1)
        attrs.append({
            'objectTypeAttributeId': key,
            'objectAttributeValues': [{'value': value}],
        })
    return attrs


# Note: Assets API uses a different base URL (api.atlassian.com), so we pass
# the full assets_base as 'base' and use relative paths.

def cmd_search(args):
    session, _, ab = assets_setup()
    data = api_post(session, ab, '/object/aql', {
        'qlQuery': args.aql,
        'resultPerPage': args.max,
        'includeAttributes': True,
    })
    objects = data.get('values', data.get('objectEntries', []))
    for obj in objects:
        otype = obj.get('objectType', {}).get('name', '?')
        print(f'{obj["id"]} [{otype}] {obj.get("label", "")}')
    emit('DONE', f'{len(objects)} objects found')


def cmd_get(args):
    session, _, ab = assets_setup()
    data = api_get(session, ab, f'/object/{args.id}')
    emit_json(data)


def cmd_create(args):
    session, _, ab = assets_setup()
    data = api_post(session, ab, '/object/create', {
        'objectTypeId': args.type_id,
        'attributes': _parse_attrs(args.attrs),
    })
    emit('OK', f'Created object {data.get("id", "")} ({data.get("label", "")})')


def cmd_update(args):
    session, _, ab = assets_setup()
    api_put(session, ab, f'/object/{args.id}', {
        'attributes': _parse_attrs(args.attrs),
    })
    emit('OK', f'Updated object {args.id}')


def cmd_delete(args):
    session, _, ab = assets_setup()
    api_delete(session, ab, f'/object/{args.id}')
    emit('OK', f'Deleted object {args.id}')


def cmd_schemas(args):
    session, _, ab = assets_setup()
    data = api_get(session, ab, '/objectschema/list')
    schemas = data.get('values', data.get('objectschemas', []))
    for s in schemas:
        print(f'{s["id"]} {s["name"]}')
    emit('DONE', f'{len(schemas)} schemas')


def cmd_schema(args):
    session, _, ab = assets_setup()
    schema_id = resolve_schema(session, ab, args.id)
    data = api_get(session, ab, f'/objectschema/{schema_id}')
    emit_json(data)


def cmd_types(args):
    session, _, ab = assets_setup()
    schema_id = resolve_schema(session, ab, args.schema_id)
    data = api_get(session, ab, f'/objectschema/{schema_id}/objecttypes/flat')
    types = data if isinstance(data, list) else data.get('values', [])
    for t in types:
        print(f'{t["id"]} {t["name"]}')
    emit('DONE', f'{len(types)} types')


def cmd_type(args):
    session, _, ab = assets_setup()
    data = api_get(session, ab, f'/objecttype/{args.id}')
    emit_json(data)


def cmd_type_create(args):
    session, _, ab = assets_setup()
    schema_id = resolve_schema(session, ab, args.schema_id)
    body = {'name': args.name, 'objectSchemaId': schema_id}
    if hasattr(args, 'description') and args.description:
        body['description'] = args.description
    if hasattr(args, 'parent_type_id') and args.parent_type_id:
        body['parentObjectTypeId'] = args.parent_type_id
    data = api_post(session, ab, '/objecttype/create', body)
    emit('OK', f'Created type {data.get("id", "")} ({args.name})')


def cmd_attrs(args):
    session, _, ab = assets_setup()
    data = api_get(session, ab, f'/objecttype/{args.type_id}/attributes')
    attrs = data if isinstance(data, list) else data.get('values', [])
    for a in attrs:
        req = '*' if a.get('minimumCardinality', 0) > 0 else ''
        type_name = a.get('type', a.get('defaultType', {}).get('name', '?'))
        if isinstance(type_name, dict):
            type_name = type_name.get('name', '?')
        print(f'{a["id"]} {a["name"]} ({type_name}) {req}'.rstrip())
    emit('DONE', f'{len(attrs)} attributes')
