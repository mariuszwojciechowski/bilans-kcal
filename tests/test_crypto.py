"""Szyfrowanie sekretów użytkownika (TODO.md „Szyfrowanie sekretów...")."""
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AppSetting, User
from app.services import crypto, settings as settings_service, transfer


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'crypto.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(email="t@t"))
    session.commit()
    yield session
    session.close()


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt("sk-ant-super-secret")
    assert token.startswith(crypto.PREFIX)
    assert token != "sk-ant-super-secret"
    assert crypto.decrypt(token) == "sk-ant-super-secret"


def test_decrypt_plaintext_passthrough():
    assert crypto.decrypt("plain-old-value") == "plain-old-value"
    assert crypto.is_encrypted("plain-old-value") is False
    assert crypto.is_encrypted(crypto.encrypt("x")) is True


def test_set_setting_does_not_store_plaintext(db):
    settings_service.set_setting(db, 1, "gemini_api_key", "AIzaSuperSecretKey")
    raw = db.execute(text(
        "SELECT value FROM app_setting WHERE user_id=1 AND key='gemini_api_key'"
    )).scalar_one()
    assert raw != "AIzaSuperSecretKey"
    assert raw.startswith(crypto.PREFIX)
    assert settings_service.get_setting(db, 1, "gemini_api_key") == "AIzaSuperSecretKey"


def test_migrate_plaintext_settings_is_idempotent(db):
    db.add(AppSetting(user_id=1, key="gemini_api_key", value="AIzaPlainLegacyKey"))
    db.commit()

    migrated = crypto.migrate_plaintext_settings(db)
    assert migrated == 1
    row = db.get(AppSetting, (1, "gemini_api_key"))
    assert row.value != "AIzaPlainLegacyKey"
    assert crypto.decrypt(row.value) == "AIzaPlainLegacyKey"

    again = crypto.migrate_plaintext_settings(db)
    assert again == 0  # już zaszyfrowane — nic do zrobienia


def test_scrub_masks_both_key_formats():
    text_in = "błąd przy AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456: timeout, " \
              "też sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ nie działa"
    out = crypto.scrub(text_in)
    assert "AIzaSy" not in out
    assert "sk-ant-" not in out
    assert "[redacted]" in out


def test_transfer_export_never_touches_app_setting(db):
    """Test-strażnik: eksport transferu nie ma żadnej ścieżki do AppSetting —
    klucze LLM (i tokeny Garmina) nie mogą tam kiedyś zacząć wyciekać."""
    settings_service.set_setting(db, 1, "gemini_api_key", "AIzaSuperSecretKey")
    payload = transfer.export_payload(db, 1)
    assert "AIzaSuperSecretKey" not in str(payload)
    assert "gemini_api_key" not in str(payload)
