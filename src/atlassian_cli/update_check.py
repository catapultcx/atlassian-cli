"""Check PyPI for newer versions of atlassian-cli (once per day)."""

import json
import os
import sys
import time
import urllib.request

from atlassian_cli import __version__

CACHE_DIR = os.path.join(os.path.expanduser('~'), '.cache', 'atlassian-cli')
CACHE_FILE = os.path.join(CACHE_DIR, 'update-check.json')
CHECK_INTERVAL = 86400  # 24 hours
PYPI_URL = 'https://pypi.org/pypi/atlassian-cli/json'


def _version_tuple(v):
    """Parse version string to tuple for comparison."""
    try:
        return tuple(int(x) for x in v.split('.'))
    except (ValueError, AttributeError):
        return (0,)


def _is_editable_install():
    """Check if the package is installed in editable/dev mode."""
    try:
        from importlib.metadata import distribution
        dist = distribution('atlassian-cli')
        # Editable installs have a direct_url.json with dir_info
        direct_url = dist.read_text('direct_url.json')
        if direct_url:
            return json.loads(direct_url).get('dir_info', {}).get('editable', False)
    except Exception:
        pass
    return False


def check_for_update():
    """Print a notice if a newer version is available. Runs silently on error."""
    try:
        if __version__ == '0.0.0-dev':
            return

        # Check cache
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                cache = json.load(f)
            if time.time() - cache.get('checked_at', 0) < CHECK_INTERVAL:
                latest = cache.get('latest', '')
                if _version_tuple(latest) > _version_tuple(__version__):
                    _print_notice(latest)
                return

        # Fetch from PyPI (short timeout to avoid slowing CLI)
        req = urllib.request.Request(PYPI_URL, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        latest = data.get('info', {}).get('version', '')

        # Cache result
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump({'checked_at': time.time(), 'latest': latest}, f)

        if _version_tuple(latest) > _version_tuple(__version__):
            _print_notice(latest)
    except Exception:
        pass  # never break the CLI for an update check


def _print_notice(latest):
    if _is_editable_install():
        hint = 'Run: git pull && pip install -e .'
    else:
        hint = 'Run: pip install --upgrade atlassian-cli'
    print(f'\033[33mUpdate available: {__version__} → {latest}. {hint}\033[0m', file=sys.stderr)
