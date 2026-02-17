"""Shared Atlassian Cloud configuration and session factory for atlassian_cli package."""

import os
import sys

import requests
from requests.auth import HTTPBasicAuth


def load_env(path=None):
    """Manually parse a .env file into a dict, skipping comments and blank lines."""
    if path is None:
        paths = [os.path.join(os.getcwd(), '.env'), os.path.join(os.path.dirname(__file__), '.env')]
    else:
        paths = [path]

    for env_path in paths:
        if os.path.exists(env_path):
            with open(env_path, 'r') as file:
                return dict(line.strip().split('=', 1) for line in file if not line.startswith('#') and '=' in line)
    return {}


def get_config():
    """Return tuple (url, email, token) from .env or environment variables."""
    env = load_env()
    url = env.get('ATLASSIAN_URL', os.environ.get('ATLASSIAN_URL')) or \
          env.get('CONFLUENCE_URL', os.environ.get('CONFLUENCE_URL'))
    email = env.get('ATLASSIAN_EMAIL', os.environ.get('ATLASSIAN_EMAIL')) or \
            env.get('CONFLUENCE_EMAIL', os.environ.get('CONFLUENCE_EMAIL'))
    token = env.get('ATLASSIAN_TOKEN', os.environ.get('ATLASSIAN_TOKEN')) or \
            env.get('CONFLUENCE_TOKEN', os.environ.get('CONFLUENCE_TOKEN'))

    if not all([url, email, token]):
        sys.stderr.write('ERR Missing ATLASSIAN_URL, ATLASSIAN_EMAIL, or ATLASSIAN_TOKEN\n'
                         'Set them in .env or as environment variables.\n')
        sys.exit(1)

    return url.rstrip('/'), email, token


def get_session(email, token):
    """Create requests.Session with HTTPBasicAuth and JSON headers."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(email, token)
    session.headers.update({
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    })
    return session


def setup():
    """Setup configuration and session, returning (session, base_url)."""
    url, email, token = get_config()
    session = get_session(email, token)
    return session, url
