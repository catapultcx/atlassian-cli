#!/usr/bin/env python3
"""Jira CLI — issue and assets management via REST APIs.

Commands:
    issue       Jira issue operations (CRUD, search, transitions)
    assets      Jira Assets/JSM operations (CRUD, schemas, types)
"""

import argparse
import sys

from atlassian_cli import jira_assets, jira_issues
from atlassian_cli.http import APIError
from atlassian_cli.output import emit_error, set_json_mode


def main():
    parser = argparse.ArgumentParser(
        prog='jira',
        description='Jira CLI — issue and assets management',
    )
    parser.add_argument('--json', action='store_true', dest='json_output',
                        help='Output as JSON for programmatic parsing')

    sub = parser.add_subparsers(dest='domain', required=True)

    # -----------------------------------------------------------------------
    # issue subcommand
    # -----------------------------------------------------------------------
    issue_parser = sub.add_parser('issue', help='Jira issue operations')
    issue_sub = issue_parser.add_subparsers(dest='command', required=True)

    p = issue_sub.add_parser('get', help='Get issue details')
    p.add_argument('key', help='Issue key (e.g. PROJ-123)')
    p.set_defaults(func=jira_issues.cmd_get)

    p = issue_sub.add_parser('create', help='Create an issue')
    p.add_argument('project', help='Project key (e.g. PROJ)')
    p.add_argument('type', help='Issue type (e.g. Task, Bug, Story)')
    p.add_argument('summary', help='Issue summary/title')
    p.add_argument('--description', help='Issue description')
    p.add_argument('--labels', nargs='*', help='Labels')
    p.add_argument('--assignee', help='Assignee account ID')
    p.add_argument('--parent', help='Parent issue key (for sub-tasks)')
    p.set_defaults(func=jira_issues.cmd_create)

    p = issue_sub.add_parser('update', help='Update issue fields')
    p.add_argument('key', help='Issue key')
    p.add_argument('--summary', help='New summary')
    p.add_argument('--description', help='New description')
    p.add_argument('--labels', nargs='*', default=None, help='Replace labels')
    p.add_argument('--assignee', help='Assignee account ID')
    p.add_argument('--fields', help='JSON string of additional fields')
    p.set_defaults(func=jira_issues.cmd_update)

    p = issue_sub.add_parser('delete', help='Delete an issue')
    p.add_argument('key', help='Issue key')
    p.set_defaults(func=jira_issues.cmd_delete)

    p = issue_sub.add_parser('search', help='Search issues with JQL')
    p.add_argument('jql', help='JQL query string')
    p.add_argument('--max', type=int, default=50, help='Max results (default: 50)')
    p.add_argument('--fields', default='summary,status,assignee,issuetype',
                   help='Comma-separated fields to return')
    p.set_defaults(func=jira_issues.cmd_search)

    p = issue_sub.add_parser('transition', help='Transition issue to new status')
    p.add_argument('key', help='Issue key')
    p.add_argument('status', help='Target status name')
    p.set_defaults(func=jira_issues.cmd_transition)

    p = issue_sub.add_parser('comment', help='Add a comment')
    p.add_argument('key', help='Issue key')
    p.add_argument('body', help='Comment text')
    p.set_defaults(func=jira_issues.cmd_comment)

    p = issue_sub.add_parser('comments', help='List comments')
    p.add_argument('key', help='Issue key')
    p.set_defaults(func=jira_issues.cmd_comments)

    # -----------------------------------------------------------------------
    # assets subcommand
    # -----------------------------------------------------------------------
    assets_parser = sub.add_parser('assets', help='Jira Assets (JSM) operations')
    assets_sub = assets_parser.add_subparsers(dest='command', required=True)

    p = assets_sub.add_parser('search', help='Search objects with AQL')
    p.add_argument('aql', help='AQL query string')
    p.add_argument('--max', type=int, default=50, help='Max results')
    p.set_defaults(func=jira_assets.cmd_search)

    p = assets_sub.add_parser('get', help='Get object by ID')
    p.add_argument('id', help='Object ID')
    p.set_defaults(func=jira_assets.cmd_get)

    p = assets_sub.add_parser('create', help='Create an object')
    p.add_argument('type_id', help='Object type ID')
    p.add_argument('attrs', nargs='+', help='Attributes as key=value pairs')
    p.set_defaults(func=jira_assets.cmd_create)

    p = assets_sub.add_parser('update', help='Update an object')
    p.add_argument('id', help='Object ID')
    p.add_argument('attrs', nargs='+', help='Attributes as key=value pairs')
    p.set_defaults(func=jira_assets.cmd_update)

    p = assets_sub.add_parser('delete', help='Delete an object')
    p.add_argument('id', help='Object ID')
    p.set_defaults(func=jira_assets.cmd_delete)

    p = assets_sub.add_parser('schemas', help='List object schemas')
    p.set_defaults(func=jira_assets.cmd_schemas)

    p = assets_sub.add_parser('schema', help='Get schema details')
    p.add_argument('id', help='Schema ID')
    p.set_defaults(func=jira_assets.cmd_schema)

    p = assets_sub.add_parser('types', help='List object types in a schema')
    p.add_argument('schema_id', help='Schema ID')
    p.set_defaults(func=jira_assets.cmd_types)

    p = assets_sub.add_parser('type', help='Get object type details')
    p.add_argument('id', help='Object type ID')
    p.set_defaults(func=jira_assets.cmd_type)

    p = assets_sub.add_parser('type-create', help='Create object type')
    p.add_argument('schema_id', help='Schema ID')
    p.add_argument('name', help='Type name')
    p.add_argument('--description', help='Type description')
    p.add_argument('--parent-type-id', help='Parent object type ID')
    p.set_defaults(func=jira_assets.cmd_type_create)

    p = assets_sub.add_parser('attrs', help='List attributes for a type')
    p.add_argument('type_id', help='Object type ID')
    p.set_defaults(func=jira_assets.cmd_attrs)

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
