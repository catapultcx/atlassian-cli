"""Shared Atlassian Cloud configuration and session factory.

Used by conflu.py (and future jira.py) for authenticated API access.
"""

import os
import sys

import requests
from requests.auth import HTTPBasicAuth


def load_env(path=None):
    """Parse a .env file into a dict. Skips comments and blank lines."""
    env = {}
    candidates = [path] if path else [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        env[k.strip()] = v.strip()
            break
    return env


def get_config(prefix='CONFLUENCE'):
    """Return (url, email, token) from .env or environment variables."""
    env = load_env()
    url = env.get(f'{prefix}_URL') or os.environ.get(f'{prefix}_URL')
    email = env.get(f'{prefix}_EMAIL') or os.environ.get(f'{prefix}_EMAIL')
    token = env.get(f'{prefix}_TOKEN') or os.environ.get(f'{prefix}_TOKEN')
    if not all([url, email, token]):
        print(
            f'ERR Missing {prefix}_URL, {prefix}_EMAIL, or {prefix}_TOKEN\n'
            f'Set them in .env or as environment variables.',
            file=sys.stderr,
        )
        sys.exit(1)
    return url.rstrip('/'), email, token


def get_session(email, token):
    """Create an authenticated requests.Session for Atlassian Cloud."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(email, token)
    session.headers.update({
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    })
    return session
