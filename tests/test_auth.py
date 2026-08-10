"""Unit tests for the APP_AUTH_TOKEN gate (app/auth.py)."""
from app.auth import auth_enabled, token_from_subprotocols, verify_token


def test_auth_disabled_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("APP_AUTH_TOKEN", raising=False)
    assert auth_enabled() is False
    assert verify_token(None) is True
    assert verify_token("anything") is True


def test_auth_enabled_requires_matching_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_AUTH_TOKEN", "secret-123")
    assert auth_enabled() is True
    assert verify_token("secret-123") is True
    assert verify_token("wrong") is False
    assert verify_token(None) is False
    assert verify_token("") is False


def test_token_from_subprotocols() -> None:
    assert token_from_subprotocols(None) is None
    assert token_from_subprotocols(["kitchen-assistant.v1"]) is None
    assert (
        token_from_subprotocols(["kitchen-assistant.v1", "kitchen-assistant.token.secret-123"])
        == "secret-123"
    )
    assert token_from_subprotocols(["kitchen-assistant.token."]) is None  # empty is not a token
