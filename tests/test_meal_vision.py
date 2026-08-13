import pytest

from app.services import meal_vision
from app.services.meal_vision import MealEstimate, MealItem


def _item(**kw) -> MealItem:
    base = dict(name="jajko", mass_g=60, kcal=90, protein_g=7, fat_g=6.5, carbs_g=0.5,
                confidence="high")
    base.update(kw)
    return MealItem(**base)


def test_estimate_total_kcal_sums_items():
    est = MealEstimate(description="x", items=[_item(kcal=90), _item(kcal=110)],
                       assumptions=[], kcal_min=150, kcal_max=280)
    assert est.kcal == 200


def test_backend_auto_prefers_gemini_when_key_set(monkeypatch):
    monkeypatch.setattr(meal_vision, "LLM_BACKEND", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert meal_vision.pick_backend() == "gemini"


def test_backend_auto_falls_back_to_claude(monkeypatch):
    monkeypatch.setattr(meal_vision, "LLM_BACKEND", "auto")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert meal_vision.pick_backend() == "claude"


def test_backend_explicit_override(monkeypatch):
    monkeypatch.setattr(meal_vision, "LLM_BACKEND", "claude")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert meal_vision.pick_backend() == "claude"


def test_gemini_without_key_raises_configured_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(meal_vision.MealVisionNotConfigured):
        meal_vision._estimate_gemini("test")


def test_unsupported_photo_format_raises():
    with pytest.raises(ValueError):
        meal_vision.estimate_from_photo(b"...", "bmp")
