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


def check_for_update():
    """Print a notice if a newer version is available. Runs silently on error."""
    try:
        # Check cache
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                cache = json.load(f)
            if time.time() - cache.get('checked_at', 0) < CHECK_INTERVAL:
                latest = cache.get('latest')
                if latest and latest != __version__:
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

        if latest and latest != __version__:
            _print_notice(latest)
    except Exception:
        pass  # never break the CLI for an update check


def _print_notice(latest):
    print(
        f'\033[33mUpdate available: {__version__} → {latest}. '
        f'Run: pip install --upgrade atlassian-cli\033[0m',
        file=sys.stderr,
    )
