"""Testy integracji Stravy — OAuth, wybór providera, synchronizacja."""
import json
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import User, UserProfile
from app.providers import get_provider_for_user
from app.providers import strava as strava_provider
from app.services import consent as consent_service
from app.services import settings as settings_service


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(email="t@t")
    session.add(user)
    profile = UserProfile(user_id=1, birth_date=date(1990, 7, 1), birth_year=1990,
                          sex='M', height_cm=180)
    session.add(profile)
    session.commit()

    # Monkeypatch crypto aby nie był wymagany klucz ENC_KEY
    from app.services import crypto
    monkeypatch.setattr(crypto, "encrypt", lambda x: f"encrypted:{x}")
    monkeypatch.setattr(crypto, "decrypt", lambda x: x.replace("encrypted:", ""))

    yield session
    session.close()


def test_tokens_present_when_saved(db):
    """tokens_present() zwraca True jeśli user ma zapisane tokeny Stravy."""
    assert not strava_provider.tokens_present(db, 1)

    blob = {"access_token": "test", "refresh_token": "refresh", "expires_at": 9999999999}
    settings_service.set_setting(db, 1, strava_provider.STRAVA_TOKENS_KEY, json.dumps(blob))

    assert strava_provider.tokens_present(db, 1)


def test_get_provider_for_user_returns_strava_when_tokens_present(db):
    """get_provider_for_user() zwraca StravaProvider gdy tokeny Stravy są."""
    blob = {"access_token": "test", "refresh_token": "refresh", "expires_at": 9999999999}
    settings_service.set_setting(db, 1, strava_provider.STRAVA_TOKENS_KEY, json.dumps(blob))

    provider = get_provider_for_user(db, 1)
    assert provider is not None
    assert isinstance(provider, strava_provider.StravaProvider)


def test_get_provider_for_user_returns_none_when_no_provider(db):
    """get_provider_for_user() zwraca None gdy user nie ma żadnego providera."""
    provider = get_provider_for_user(db, 1)
    assert provider is None


def test_consent_strava_independent_from_llm(db):
    """Zgoda na Stravę jest niezależna od zgody na LLM."""
    llm_consent = consent_service.grant(db, 1, consent_service.LLM_PHOTOS)
    assert consent_service.has_consent(db, 1, consent_service.LLM_PHOTOS)
    assert not consent_service.has_consent(db, 1, consent_service.STRAVA)

    strava_consent = consent_service.grant(db, 1, consent_service.STRAVA)
    assert consent_service.has_consent(db, 1, consent_service.LLM_PHOTOS)
    assert consent_service.has_consent(db, 1, consent_service.STRAVA)

    # Wycofanie Stravy nie wpływa na LLM
    consent_service.withdraw(db, 1, consent_service.STRAVA)
    assert consent_service.has_consent(db, 1, consent_service.LLM_PHOTOS)
    assert not consent_service.has_consent(db, 1, consent_service.STRAVA)


def test_strava_provider_get_daily_summary_returns_none(db):
    """StravaProvider.get_daily_summary() zwraca pusty object (Strava nie ma dziennych sum)."""
    blob = {"access_token": "test", "refresh_token": "refresh", "expires_at": 9999999999}
    settings_service.set_setting(db, 1, strava_provider.STRAVA_TOKENS_KEY, json.dumps(blob))

    provider = strava_provider.StravaProvider(1, db)
    summary = provider.get_daily_summary(date(2026, 1, 1))

    assert summary.date == date(2026, 1, 1)
    assert summary.kcal_total is None
    assert summary.kcal_active is None
    assert summary.kcal_bmr is None
    assert summary.steps is None


def test_strava_provider_get_weights_returns_empty(db):
    """StravaProvider.get_weights() zwraca [] (Strava nie jest źródłem wagi)."""
    blob = {"access_token": "test", "refresh_token": "refresh", "expires_at": 9999999999}
    settings_service.set_setting(db, 1, strava_provider.STRAVA_TOKENS_KEY, json.dumps(blob))

    provider = strava_provider.StravaProvider(1, db)
    weights = provider.get_weights(date(2026, 1, 1), date(2026, 1, 31))

    assert weights == []


def test_strava_provider_missing_tokens_raises(db):
    """StravaProvider bez tokeny rzuca RuntimeError."""
    provider = strava_provider.StravaProvider(1, db)
    with pytest.raises(RuntimeError, match="Brak podłączonego konta Stravy"):
        provider.get_activities(date(2026, 1, 1), date(2026, 1, 31))
