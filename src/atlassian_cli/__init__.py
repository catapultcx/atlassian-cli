"""Atlassian Cloud CLI tools for Confluence and Jira."""

try:
    from importlib.metadata import version
    __version__ = version('atlassian-cli')
except Exception:
    __version__ = '0.0.0-dev'
