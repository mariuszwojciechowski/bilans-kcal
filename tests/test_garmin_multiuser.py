"""Garmin per-user: tokeny sesji i stan MFA muszą być rozdzielone między
użytkownikami. Od planu „Szyfrowanie sekretów" (część B) tokeny nie leżą
jako pliki na dysku — są zaszyfrowanym blobem w AppSetting, materializowanym
do katalogu tymczasowego tylko na czas logowania. Sam GarminProvider testujemy
pod mockowaną biblioteką `garminconnect.Garmin` — nie chcemy uderzać w
prawdziwe Garmin Connect."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import User
from app.providers import garmin as g
from app.services import settings as settings_service


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'garmin.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(email="t@t"))
    session.commit()
    g._mfa_state.clear()
    yield session
    session.close()
    g._mfa_state.clear()


def _fake_dump(tmpdir):
    """Zamiast prawdziwego api.client.dump(tmpdir) — zapisuje jeden plik token."""
    import pathlib
    pathlib.Path(tmpdir, "oauth.json").write_text('{"token": "abc"}')


def test_tokens_present_is_per_user(db):
    fake_api = MagicMock()
    fake_api.login.return_value = ("ok", None)
    fake_api.client.dump.side_effect = _fake_dump
    with patch.object(g, "Garmin", return_value=fake_api):
        assert g.interactive_login_start(db, "a@a", "haslo", user_id=1) == "ok"

    assert g.tokens_present(db, 1) is True
    assert g.tokens_present(db, 2) is False   # user 2 nie widzi tokenów usera 1


def test_tokens_are_encrypted_in_db(db):
    fake_api = MagicMock()
    fake_api.login.return_value = ("ok", None)
    fake_api.client.dump.side_effect = _fake_dump
    with patch.object(g, "Garmin", return_value=fake_api):
        g.interactive_login_start(db, "a@a", "haslo", user_id=1)

    from sqlalchemy import text
    raw = db.execute(text(
        "SELECT value FROM app_setting WHERE user_id=1 AND key='garmin_tokens'"
    )).scalar_one()
    assert "oauth.json" not in raw  # nie plaintext JSON tokenów
    assert settings_service.get_setting(db, 1, "garmin_tokens") is not None


def test_mfa_state_is_isolated_between_users(db):
    """User A zaczyna MFA, user B próbuje wysłać kod → dostaje błąd zamiast
    przypadkiem wskoczyć w cudzą sesję logowania."""
    fake_api_a = MagicMock()
    fake_api_a.login.return_value = ("needs_mfa", "state-a")

    with patch.object(g, "Garmin", return_value=fake_api_a):
        assert g.interactive_login_start(db, "a@a", "x", user_id=1) == "mfa"

    with pytest.raises(g.GarminNotLoggedIn):
        g.interactive_login_mfa(db, "123456", user_id=2)

    # user 1 nadal widzi swoje pending MFA
    fake_api_a.resume_login.return_value = None
    fake_api_a.client.dump.side_effect = _fake_dump
    g.interactive_login_mfa(db, "123456", user_id=1)
    fake_api_a.resume_login.assert_called_once_with("state-a", "123456")


def test_garmin_provider_uses_per_user_tokens(db):
    fake_api = MagicMock()
    fake_api.login.return_value = ("ok", None)
    fake_api.client.dump.side_effect = _fake_dump
    with patch.object(g, "Garmin", return_value=fake_api):
        g.interactive_login_start(db, "a@a", "haslo", user_id=42)

        provider = g.GarminProvider(user_id=42, db=db)
        provider._client()

    # login() materializuje tokeny do jednorazowego katalogu tymczasowego
    # (posprzątanego już po powrocie z _client()), nie do stałej ścieżki na dysku.
    # Pierwsze wywołanie to interactive_login_start (bez argumentów), drugie
    # to GarminProvider._client() (z katalogiem tymczasowym).
    assert fake_api.login.call_count == 2
    call_dir = fake_api.login.call_args_list[1][0][0]
    assert "fk-garmin-" in call_dir


def test_garmin_provider_without_tokens_raises(db):
    provider = g.GarminProvider(user_id=99, db=db)
    with pytest.raises(g.GarminNotLoggedIn):
        provider._client()


def test_migrate_tokens_dirs_to_db(db, tmp_path, monkeypatch):
    from app import config

    tokens_dir = tmp_path / "garth"
    monkeypatch.setattr(config, "GARMIN_TOKENS_DIR", tokens_dir)
    monkeypatch.setattr(g, "GARMIN_TOKENS_DIR", tokens_dir)
    user_dir = tokens_dir / "5"
    user_dir.mkdir(parents=True)
    (user_dir / "oauth.json").write_text('{"token": "old"}')

    migrated = g.migrate_tokens_dirs_to_db(db)
    assert migrated == 1
    assert g.tokens_present(db, 5) is True
    assert not user_dir.exists()

    # idempotentne: drugie wywołanie nic nie robi (katalog już nie istnieje)
    assert g.migrate_tokens_dirs_to_db(db) == 0
