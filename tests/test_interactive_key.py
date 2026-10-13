"""Interactive API-key entry: TTY prompt via getpass, non-TTY keeps the
existing error, --api-key wins over the environment."""
import sys
from types import SimpleNamespace

import pytest

import lgmt.cli as cli
from lgmt.config import resolve_settings


def _args(**kw):
    defaults = {"mock": None, "api_key": None}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_tty_prompt_supplies_key(monkeypatch):
    monkeypatch.delenv("LGMT_API_KEY", raising=False)
    monkeypatch.setenv("LGMT_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    prompts = []
    monkeypatch.setattr(
        "getpass.getpass", lambda prompt: prompts.append(prompt) or "sk-typed"
    )
    settings = resolve_settings(None, {})
    assert settings.api_key is None

    client, _ = cli._resolve_client(_args(), settings, require_real=True)

    assert prompts == [cli._KEY_PROMPT]
    assert client.api_key == "sk-typed"
    assert settings.api_key == "sk-typed"  # in memory only


def test_non_tty_keeps_error_without_prompt(monkeypatch):
    monkeypatch.delenv("LGMT_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    called = []
    monkeypatch.setattr(
        "getpass.getpass", lambda prompt: called.append(prompt) or "sk-x"
    )
    settings = resolve_settings(None, {})

    with pytest.raises(SystemExit) as exc:
        cli._resolve_client(_args(), settings, require_real=True)

    assert called == []  # no prompt off a TTY
    assert "no API key configured" in str(exc.value)
    assert "--api-key" in str(exc.value)  # mentioned flag must exist


def test_api_key_flag_beats_env(monkeypatch):
    monkeypatch.setenv("LGMT_API_KEY", "sk-from-env")
    monkeypatch.setenv("LGMT_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    settings = resolve_settings(None, {"api_key": "sk-from-flag"})

    client, _ = cli._resolve_client(_args(api_key="sk-from-flag"), settings, require_real=True)

    assert client.api_key == "sk-from-flag"
    assert client.base_url == "https://example.test/v1"


def test_env_key_used_without_prompt(monkeypatch):
    monkeypatch.setenv("LGMT_API_KEY", "sk-from-env")
    monkeypatch.setenv("LGMT_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    prompts = []
    monkeypatch.setattr("getpass.getpass", lambda p: prompts.append(p) or "")
    settings = resolve_settings(None, {})

    client, _ = cli._resolve_client(_args(), settings, require_real=True)

    assert prompts == []  # existing key skips the prompt entirely
    assert client.api_key == "sk-from-env"


def test_mock_never_prompts(monkeypatch):
    monkeypatch.delenv("LGMT_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    prompts = []
    monkeypatch.setattr("getpass.getpass", lambda p: prompts.append(p) or "sk-x")

    client, name = cli._resolve_client(
        _args(mock="consistent"), resolve_settings(None, {}), require_real=True
    )

    assert prompts == []
    assert name == "mock-consistent"
    assert client.persona == "consistent"


def test_empty_tty_input_falls_back_to_error(monkeypatch):
    monkeypatch.delenv("LGMT_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda p: "")
    with pytest.raises(SystemExit):
        cli._resolve_client(_args(), resolve_settings(None, {}), require_real=True)
