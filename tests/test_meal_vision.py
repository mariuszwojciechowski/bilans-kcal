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


# ── Vertex AI (Gemini z konta serwera, bez kluczy) ────────────────────────

class _FakeModels:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return type("Resp", (), {"parsed": self.parsed})()


class _FakeClient:
    def __init__(self, parsed):
        self.models = _FakeModels(parsed)


def _vertex_env(monkeypatch, project="proj-test"):
    monkeypatch.setattr(meal_vision, "LLM_BACKEND", "auto")
    monkeypatch.setattr(meal_vision, "VERTEX_PROJECT", project)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_auto_picks_vertex_without_user_key_and_is_configured(monkeypatch):
    _vertex_env(monkeypatch)
    assert meal_vision.pick_backend(None, None) == "vertex"
    assert meal_vision.llm_configured(None, None) is True        # żaden klucz
    # klucz użytkownika wygrywa z kontem serwera
    assert meal_vision.pick_backend("AIza-user", None) == "gemini"


def test_auto_without_project_keeps_old_behaviour(monkeypatch):
    _vertex_env(monkeypatch, project=None)
    assert meal_vision.pick_backend(None, None) == "claude"
    assert meal_vision.llm_configured(None, None) is False


def test_vertex_client_built_with_adc_and_no_key(monkeypatch):
    _vertex_env(monkeypatch)
    monkeypatch.setattr(meal_vision, "VERTEX_LOCATION", "europe-west1")
    captured = {}

    class FakeGenai:
        class types:
            @staticmethod
            def HttpOptions(**kw):
                return ("http_options", kw)

        @staticmethod
        def Client(**kw):
            captured.update(kw)
            return "client"

    import sys
    monkeypatch.setitem(sys.modules, "google.genai", FakeGenai)
    monkeypatch.setattr(sys.modules["google"], "genai", FakeGenai, raising=False)
    assert meal_vision.gemini_client("vertex") == "client"
    assert captured == {
        "vertexai": True, "project": "proj-test", "location": "europe-west1",
        # per-model timeout z upstreamu obowiązuje też na ścieżce ADC
        "http_options": ("http_options", {"timeout": meal_vision.PER_MODEL_TIMEOUT_S * 1000}),
    }


def test_forced_vertex_without_project_is_not_configured(monkeypatch):
    _vertex_env(monkeypatch, project=None)
    monkeypatch.setattr(meal_vision, "LLM_BACKEND", "vertex")
    assert meal_vision.pick_backend(None, None) == "vertex"
    assert meal_vision.llm_configured(None, None) is False   # trafia do kolejki jako no_key
    assert meal_vision.classify_error(meal_vision.MealVisionNotConfigured("x")) == "no_key"


def test_estimate_gemini_without_client_resolves_vertex_via_pick_backend(monkeypatch):
    _vertex_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")       # klucz w env nie może wygrać z projektem
    seen = {}
    est = MealEstimate(description="x", items=[_item()], assumptions=[], kcal_min=1, kcal_max=2)

    def fake_client(backend, key=None):
        seen["backend"] = backend
        return _FakeClient(est)

    monkeypatch.setattr(meal_vision, "gemini_client", fake_client)
    out, _model = meal_vision._estimate_gemini("x")
    assert out is est
    assert seen["backend"] == "vertex"


def test_estimate_from_text_uses_injected_fake_client(monkeypatch):
    _vertex_env(monkeypatch)
    est = MealEstimate(description="jajko", items=[_item()], assumptions=[],
                       kcal_min=80, kcal_max=100)
    fake = _FakeClient(est)
    monkeypatch.setattr(meal_vision, "gemini_client", lambda backend, key=None: fake)
    out, model = meal_vision.estimate_from_text("jajko sadzone")
    assert out is est
    assert model == meal_vision.GEMINI_MODELS[0]
    call = fake.models.calls[0]
    assert call["model"] == meal_vision.GEMINI_MODELS[0]
    assert "jajko sadzone" in call["contents"][-1]
