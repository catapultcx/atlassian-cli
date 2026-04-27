"""Tests for atlassian_cli.config."""

import pytest

from atlassian_cli.config import get_config, get_session, load_env, setup


class TestLoadEnv:
    def test_parses_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n# comment\n\nKEY3=val=ue3\n")
        result = load_env(str(env_file))
        assert result == {"KEY1": "value1", "KEY2": "value2", "KEY3": "val=ue3"}

    def test_returns_empty_when_missing(self, tmp_path):
        result = load_env(str(tmp_path / "nonexistent"))
        assert result == {}

    def test_skips_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nVALID=yes\n")
        result = load_env(str(env_file))
        assert result == {"VALID": "yes"}


class TestGetConfig:
    def test_reads_atlassian_prefix(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ATLASSIAN_URL=https://test.atlassian.net\n"
            "ATLASSIAN_EMAIL=user@test.com\n"
            "ATLASSIAN_TOKEN=tok123\n"
        )
        monkeypatch.chdir(tmp_path)
        url, email, token = get_config()
        assert url == "https://test.atlassian.net"
        assert email == "user@test.com"
        assert token == "tok123"

    def test_falls_back_to_confluence_prefix(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "CONFLUENCE_URL=https://old.atlassian.net\n"
            "CONFLUENCE_EMAIL=old@test.com\n"
            "CONFLUENCE_TOKEN=oldtok\n"
        )
        monkeypatch.chdir(tmp_path)
        url, email, token = get_config()
        assert url == "https://old.atlassian.net"
        assert email == "old@test.com"

    def test_strips_trailing_slash(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ATLASSIAN_URL=https://test.atlassian.net/\n"
            "ATLASSIAN_EMAIL=u@t.com\n"
            "ATLASSIAN_TOKEN=t\n"
        )
        monkeypatch.chdir(tmp_path)
        url, _, _ = get_config()
        assert url == "https://test.atlassian.net"

    def test_loads_from_xdg_config(self, monkeypatch, tmp_path):
        xdg = tmp_path / "xdg"
        cfg = xdg / "atlassian-cli" / "config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            "ATLASSIAN_URL=https://xdg.atlassian.net\n"
            "ATLASSIAN_EMAIL=xdg@test.com\n"
            "ATLASSIAN_TOKEN=xdgtok\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("ATLASSIAN_CLI_CONFIG", raising=False)
        url, email, token = get_config()
        assert url == "https://xdg.atlassian.net"
        assert email == "xdg@test.com"
        assert token == "xdgtok"

    def test_explicit_override_wins(self, monkeypatch, tmp_path):
        override = tmp_path / "override.env"
        override.write_text(
            "ATLASSIAN_URL=https://override.atlassian.net\n"
            "ATLASSIAN_EMAIL=o@t.com\n"
            "ATLASSIAN_TOKEN=otok\n"
        )
        # cwd has a .env that should be ignored when override is set
        (tmp_path / ".env").write_text(
            "ATLASSIAN_URL=https://cwd.atlassian.net\n"
            "ATLASSIAN_EMAIL=c@t.com\n"
            "ATLASSIAN_TOKEN=ctok\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ATLASSIAN_CLI_CONFIG", str(override))
        url, _, _ = get_config()
        assert url == "https://override.atlassian.net"

    def test_exits_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.delenv("ATLASSIAN_CLI_CONFIG", raising=False)
        monkeypatch.delenv("ATLASSIAN_URL", raising=False)
        monkeypatch.delenv("ATLASSIAN_EMAIL", raising=False)
        monkeypatch.delenv("ATLASSIAN_TOKEN", raising=False)
        monkeypatch.delenv("CONFLUENCE_URL", raising=False)
        monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
        monkeypatch.delenv("CONFLUENCE_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            get_config()


class TestGetSession:
    def test_session_has_auth(self):
        s = get_session("user@test.com", "tok")
        assert s.auth is not None
        assert s.headers["Accept"] == "application/json"


class TestSetup:
    def test_returns_session_and_url(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ATLASSIAN_URL=https://test.atlassian.net\n"
            "ATLASSIAN_EMAIL=u@t.com\n"
            "ATLASSIAN_TOKEN=t\n"
        )
        monkeypatch.chdir(tmp_path)
        session, base = setup()
        assert base == "https://test.atlassian.net"
        assert session.auth is not None
