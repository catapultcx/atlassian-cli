"""Shared HTTP helpers for API calls in the atlassian_cli package."""

import random
import sys
import time


class APIError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __str__(self):
        return f'HTTP {self.status}: {self.body[:200]}'


MAX_RETRIES = 5
BASE_DELAY = 2


def _retry(func, *args, **kwargs):
    """Execute an HTTP request with retry on 429 (rate limit) responses.

    Uses exponential backoff with jitter as recommended by Atlassian.
    """
    for attempt in range(MAX_RETRIES + 1):
        response = func(*args, **kwargs)
        if response.status_code != 429:
            return response
        if attempt == MAX_RETRIES:
            return response  # let caller handle the final 429
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            delay = int(retry_after)
        else:
            delay = BASE_DELAY * (2 ** attempt)
        delay *= random.uniform(0.7, 1.3)  # jitter
        reason = response.headers.get('RateLimit-Reason', 'unknown')
        print(f'Rate limited ({reason}), retrying in {delay:.1f}s '
              f'(attempt {attempt + 1}/{MAX_RETRIES})...', file=sys.stderr)
        time.sleep(delay)
    return response  # unreachable, but satisfies type checkers


def api_get(session, base, path, **params):
    response = _retry(session.get, f'{base}{path}', params=params or None)
    if response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)


def api_post(session, base, path, data):
    response = _retry(session.post, f'{base}{path}', json=data)
    if response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)


def api_put(session, base, path, data):
    response = _retry(session.put, f'{base}{path}', json=data)
    if response.status_code == 204:
        return None
    elif response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)


def api_delete(session, base, path, **params):
    response = _retry(session.delete, f'{base}{path}', params=params or None)
    if response.status_code == 204:
        return None
    elif response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)
