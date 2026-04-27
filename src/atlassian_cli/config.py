"""Shared Atlassian Cloud configuration and session factory for atlassian_cli package."""

import os
import sys

import requests
from requests.auth import HTTPBasicAuth


def _config_search_paths():
    """Return ordered list of paths to look for a .env / config file.

    Search order (first match wins):
      1. ATLASSIAN_CLI_CONFIG env var (explicit override)
      2. ./.env in the current working directory
      3. $XDG_CONFIG_HOME/atlassian-cli/config (XDG default ~/.config/...)
      4. ~/.atlassian-cli/config (legacy/dotfile location)
      5. <package_dir>/.env (last-ditch fallback for editable installs)
    """
    paths = []
    override = os.environ.get('ATLASSIAN_CLI_CONFIG')
    if override:
        paths.append(override)
    paths.append(os.path.join(os.getcwd(), '.env'))
    xdg = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    paths.append(os.path.join(xdg, 'atlassian-cli', 'config'))
    paths.append(os.path.expanduser('~/.atlassian-cli/config'))
    paths.append(os.path.join(os.path.dirname(__file__), '.env'))
    return paths


def load_env(path=None):
    """Parse a .env-style file into a dict, skipping comments and blank lines."""
    paths = [path] if path else _config_search_paths()
    for env_path in paths:
        if env_path and os.path.exists(env_path):
            with open(env_path, 'r') as file:
                return dict(
                    line.strip().split('=', 1)
                    for line in file
                    if not line.startswith('#') and '=' in line
                )
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
