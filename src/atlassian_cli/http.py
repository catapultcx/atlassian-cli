"""Shared HTTP helpers for API calls in the atlassian_cli package."""

class APIError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __str__(self):
        return f'HTTP {self.status}: {self.body[:200]}'

def api_get(session, base, path, **params):
    response = session.get(f'{base}{path}', params=params or None)
    if response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)

def api_post(session, base, path, data):
    response = session.post(f'{base}{path}', json=data)
    if response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)

def api_put(session, base, path, data):
    response = session.put(f'{base}{path}', json=data)
    if response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)

def api_delete(session, base, path):
    response = session.delete(f'{base}{path}')
    if response.status_code == 204:
        return None
    elif response.ok:
        return response.json()
    raise APIError(response.status_code, response.text)
