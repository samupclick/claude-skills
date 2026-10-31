import pytest

from adapters.env import UnknownBackend
from adapters.turnstile import get_turnstile


def test_pass_backend_always_passes(monkeypatch):
    monkeypatch.setenv("TURNSTILE_BACKEND", "pass")
    assert get_turnstile().verify("any-token", remote_ip="127.0.0.1") is True


def test_unknown_backend_names_variable(monkeypatch):
    monkeypatch.setenv("TURNSTILE_BACKEND", "hcaptcha")
    with pytest.raises(UnknownBackend, match="TURNSTILE_BACKEND"):
        get_turnstile()
