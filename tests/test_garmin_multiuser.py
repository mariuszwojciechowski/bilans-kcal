"""Garmin per-user: katalog tokenów i stan MFA muszą być rozdzielone
między użytkownikami. Sam GarminProvider testujemy pod mockowaną biblioteką
`garminconnect.Garmin` — nie chcemy uderzać w prawdziwe Garmin Connect."""

from unittest.mock import MagicMock, patch

import pytest

from app import config
from app.providers import garmin as g


@pytest.fixture
def tmp_tokens(tmp_path, monkeypatch):
    """Przekierowanie GARMIN_TOKENS_DIR na tmp_path — nie dotykamy ~/.fit-krasnal."""
    monkeypatch.setattr(config, "GARMIN_TOKENS_DIR", tmp_path)
    g._mfa_state.clear()
    yield tmp_path
    g._mfa_state.clear()


def test_tokens_present_is_per_user(tmp_tokens):
    (tmp_tokens / "1").mkdir()
    (tmp_tokens / "1" / "oauth.json").write_text("{}")

    assert g.tokens_present(1) is True
    assert g.tokens_present(2) is False   # user 2 nie widzi tokenów usera 1


def test_interactive_login_writes_tokens_to_user_dir(tmp_tokens):
    fake_api = MagicMock()
    fake_api.login.return_value = ("ok", None)
    with patch.object(g, "Garmin", return_value=fake_api):
        assert g.interactive_login_start("a@a", "haslo", user_id=7) == "ok"

    fake_api.client.dump.assert_called_once_with(str(tmp_tokens / "7"))


def test_mfa_state_is_isolated_between_users(tmp_tokens):
    """User A zaczyna MFA, user B próbuje wysłać kod → dostaje błąd zamiast
    przypadkiem wskoczyć w cudzą sesję logowania."""
    fake_api_a = MagicMock()
    fake_api_a.login.return_value = ("needs_mfa", "state-a")

    with patch.object(g, "Garmin", return_value=fake_api_a):
        assert g.interactive_login_start("a@a", "x", user_id=1) == "mfa"

    with pytest.raises(g.GarminNotLoggedIn):
        g.interactive_login_mfa("123456", user_id=2)

    # user 1 nadal widzi swoje pending MFA
    fake_api_a.resume_login.return_value = None
    g.interactive_login_mfa("123456", user_id=1)
    fake_api_a.resume_login.assert_called_once_with("state-a", "123456")


def test_garmin_provider_uses_per_user_tokens(tmp_tokens):
    fake_api = MagicMock()
    with patch.object(g, "Garmin", return_value=fake_api):
        provider = g.GarminProvider(user_id=42)
        provider._client()

    fake_api.login.assert_called_once_with(str(tmp_tokens / "42"))
