"""Provides shared output formatting for atlassian_cli package with both text and JSON modes."""

import json
import sys

_json_mode = False

def set_json_mode(enabled: bool):
    global _json_mode
    _json_mode = enabled

def emit(prefix, message, data=None):
    if _json_mode:
        output_data = {'status': prefix.lower(), 'message': message}
        if data:
            output_data.update(data)
        print(json.dumps(output_data))
    else:
        print(f'{prefix} {message}')

def emit_json(data):
    print(json.dumps(data, indent=2))

def emit_error(message):
    if _json_mode:
        print(json.dumps({'status': 'error', 'message': message}), file=sys.stderr)
    else:
        print(f'ERR {message}', file=sys.stderr)
