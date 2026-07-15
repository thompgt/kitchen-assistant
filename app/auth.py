"""Shared-token gate for the voice WebSocket.

Deliberately not a user-account system: this app is a single-deployment
kitchen appliance (one container, LAN or personal use), not a multi-tenant
SaaS. Per-session state isolation (StateManager keyed by session_id) already
gives each connection its own recipe/timer state — "multi-user" in the sense
of concurrent independent sessions works with zero auth. APP_AUTH_TOKEN adds
the one thing that was actually missing: a gate so an exposed deployment
can't be used by strangers to burn your Gemini API quota.
"""
import hmac
import os


def auth_enabled() -> bool:
    return bool(os.getenv("APP_AUTH_TOKEN"))


def verify_token(token: str | None) -> bool:
    """True if access is allowed: auth disabled, or token matches APP_AUTH_TOKEN."""
    expected = os.getenv("APP_AUTH_TOKEN")
    if not expected:
        return True
    if not token:
        return False
    return hmac.compare_digest(token, expected)
