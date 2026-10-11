"""Moduł M4: szacowanie kcal i makroskładników posiłku ze zdjęcia (lub opisu tekstowego)
przez model wizyjny LLM. Model samodzielnie identyfikuje składniki, masy i wartości
odżywcze (bez zewnętrznej bazy żywieniowej — decyzja D6). Wynik zawsze z przedziałem
kcal_min–kcal_max i listą założeń do weryfikacji przez użytkownika.

Backend wymienny (FIT_KRASNAL_LLM = auto | claude | gemini):
- claude — Anthropic API (ANTHROPIC_API_KEY),
- gemini — Google AI Studio (GEMINI_API_KEY / GOOGLE_API_KEY; ma darmowy tier,
  z kaskadą modeli od najlepszego do najbardziej wydajnego limitami — patrz
  config.GEMINI_MODELS i _estimate_gemini).
- vertex — ten sam Gemini przez Vertex AI z konta serwera (ADC), bez kluczy;
  wybierany w auto, gdy jest FIT_KRASNAL_VERTEX_PROJECT i user nie ma klucza.
W trybie auto wybierany jest gemini, jeśli jego klucz jest ustawiony, inaczej claude."""

import base64
import logging
import os
import time
from typing import Literal

from pydantic import BaseModel, Field

from ..config import GEMINI_MODELS, LLM_BACKEND, VERTEX_LOCATION, VERTEX_PROJECT, VISION_MODEL
from . import crypto

logger = logging.getLogger(__name__)

# A hung provider call must not hold the user (or the queue worker) forever:
# one model gets PER_MODEL_TIMEOUT_S, the whole Gemini cascade TOTAL_DEADLINE_S.
PER_MODEL_TIMEOUT_S = 30
TOTAL_DEADLINE_S = 75

MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


class MealItem(BaseModel):
    name: str = Field(description="Nazwa składnika po polsku")
    mass_g: float = Field(description="Szacowana masa w gramach")
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float = 0
    sugars_g: float = Field(default=0, description="Cukry wolne/dodane")
    confidence: Literal["low", "medium", "high"]


class MealEstimate(BaseModel):
    description: str = Field(description="Krótki opis posiłku po polsku")
    items: list[MealItem]
    assumptions: list[str] = Field(
        description="Założenia przyjęte przy szacowaniu (np. ilość oleju, cukier w napoju)"
    )
    kcal_min: float = Field(description="Dolna granica realistycznego przedziału kcal")
    kcal_max: float = Field(description="Górna granica realistycznego przedziału kcal")

    @property
    def kcal(self) -> float:
        return sum(i.kcal for i in self.items)


SYSTEM = """Jesteś ekspertem dietetykiem szacującym wartości odżywcze posiłków.
Analizujesz zdjęcie lub opis posiłku i zwracasz strukturalne oszacowanie.

Zasady:
- Zidentyfikuj każdy widoczny/opisany składnik osobno, oszacuj jego masę w gramach
  na podstawie proporcji talerza/naczynia i typowych porcji.
- Uwzględniaj tłuszcz niewidoczny wprost (olej do smażenia, masło, dressing) — dodaj go
  jako osobny składnik i odnotuj w assumptions.
- kcal_min/kcal_max: realistyczny przedział niepewności całego posiłku (typowo ±25-40%
  wokół sumy; węższy tylko dla produktów paczkowanych o znanej gramaturze).
- Wartości per składnik mają być spójne: kcal ≈ 4*białko + 9*tłuszcz + 4*węglowodany.
- Odpowiadaj po polsku (nazwy składników, opis, założenia)."""


class MealVisionNotConfigured(RuntimeError):
    pass


def classify_error(exc: Exception) -> str:
    """Krótka kategoria błędu do wyświetlenia nad kolejką (PendingMeal
    .last_error_kind) — rozróżnia sprawy, które użytkownik może naprawić
    (klucz), od przejściowych (limit/przeciążenie), gdzie trzeba tylko czekać."""
    if isinstance(exc, MealVisionNotConfigured):
        return "no_key"       # brak klucza albo projektu Vertex — do naprawy przez usera/operatora
    text = str(exc)
    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return "invalid_key"
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return "rate_limited"
    return "error"


def _env_gemini_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _env_anthropic_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")


def pick_backend(gemini_key: str | None = None, anthropic_key: str | None = None) -> str:
    """Wybór backendu. Wybór wg config (LLM_BACKEND) jest globalny.
    W trybie auto: gemini przy kluczu użytkownika; potem vertex, gdy jest
    projekt (konto serwera, bez kluczy); potem gemini z klucza w env; inaczej claude."""
    if LLM_BACKEND in ("claude", "gemini", "vertex"):
        return LLM_BACKEND
    if gemini_key:
        return "gemini"
    if VERTEX_PROJECT:
        return "vertex"
    if _env_gemini_key():
        return "gemini"
    return "claude"


def llm_configured(gemini_key: str | None = None, anthropic_key: str | None = None) -> bool:
    """Czy jest sens próbować wywołania LLM (klucz albo konto serwera w vertex)."""
    backend = pick_backend(gemini_key, anthropic_key)
    if backend == "vertex":
        return bool(VERTEX_PROJECT)   # ADC konta serwera — klucz zbędny, ale projekt musi być
    if backend == "gemini":
        return bool(gemini_key or _env_gemini_key())
    return bool(anthropic_key or _env_anthropic_key())


# ── Publiczne API ─────────────────────────────────────────────────────────

def estimate_from_photo(image_bytes: bytes, ext: str, note: str | None = None,
                        gemini_key: str | None = None,
                        anthropic_key: str | None = None) -> tuple[MealEstimate, str]:
    """Zwraca (oszacowanie, nazwa modelu, który je wyprodukował) — model do
    wyświetlenia na ekranie „sprawdź i popraw" (nie do zapisu w Meal)."""
    media_type = MEDIA_TYPES.get(ext.lower().lstrip("."))
    if media_type is None:
        raise ValueError(f"Nieobsługiwany format zdjęcia: {ext}")
    prompt = "Oszacuj wartości odżywcze posiłku ze zdjęcia." + (
        f" Uwaga użytkownika: {note}" if note else ""
    )
    backend = pick_backend(gemini_key, anthropic_key)
    if backend in ("gemini", "vertex"):
        return _estimate_gemini(prompt, image_bytes, media_type,
                                client=gemini_client(backend, gemini_key))
    return _estimate_claude(prompt, image_bytes, media_type, api_key=anthropic_key)


def estimate_from_text(description: str,
                        gemini_key: str | None = None,
                        anthropic_key: str | None = None) -> tuple[MealEstimate, str]:
    prompt = f"Oszacuj wartości odżywcze posiłku: {description}"
    backend = pick_backend(gemini_key, anthropic_key)
    if backend in ("gemini", "vertex"):
        return _estimate_gemini(prompt, client=gemini_client(backend, gemini_key))
    return _estimate_claude(prompt, api_key=anthropic_key)


# ── Backend: Claude (Anthropic API) ───────────────────────────────────────

def _estimate_claude(
    prompt: str, image_bytes: bytes | None = None, media_type: str | None = None,
    api_key: str | None = None,
) -> tuple[MealEstimate, str]:
    import anthropic

    try:
        kwargs = {"timeout": float(PER_MODEL_TIMEOUT_S * 2), "max_retries": 1}
        if api_key:
            kwargs["api_key"] = api_key
        client = anthropic.Anthropic(**kwargs)
        client._validate_headers({}, {})  # wymusza rozwiązanie uwierzytelnienia
    except TypeError as exc:
        raise MealVisionNotConfigured(
            "Brak klucza Claude API — ustaw ANTHROPIC_API_KEY albo klucz Gemini "
            "(GEMINI_API_KEY; patrz .env.example)."
        ) from exc

    content: list[dict] = []
    if image_bytes is not None:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(image_bytes).decode(),
                },
            }
        )
    content.append({"type": "text", "text": prompt})

    response = client.messages.parse(
        model=VISION_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_format=MealEstimate,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model odmówił analizy zdjęcia.")
    estimate = response.parsed_output
    if estimate is None:
        raise RuntimeError("Nie udało się sparsować odpowiedzi modelu.")
    return estimate, VISION_MODEL


# ── Backend: Gemini (Google AI Studio z kluczem albo Vertex AI z ADC) ─────

def gemini_client(backend: str = "gemini", api_key: str | None = None):
    """Klient google-genai: `vertex` → Vertex AI z Application Default Credentials
    konta serwera (projekt/region z env, bez klucza); inaczej klucz API.
    Oba tryby dostają per-model timeout (PER_MODEL_TIMEOUT_S z upstreamu) — zawieszone
    wywołanie nie może trzymać workera kolejki ani wątku żądania."""
    from google import genai
    from google.genai import types

    http_options = types.HttpOptions(timeout=PER_MODEL_TIMEOUT_S * 1000)  # ms
    if backend == "vertex":
        if not VERTEX_PROJECT:
            raise MealVisionNotConfigured(
                "Tryb vertex wymaga FIT_KRASNAL_VERTEX_PROJECT (projekt GCP z Vertex AI)."
            )
        return genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION,
                            http_options=http_options)
    key = api_key or _env_gemini_key()
    if not key:
        raise MealVisionNotConfigured(
            "Brak klucza Gemini — ustaw GEMINI_API_KEY (darmowy klucz: aistudio.google.com)."
        )
    return genai.Client(api_key=key, http_options=http_options)


def _estimate_gemini(
    prompt: str, image_bytes: bytes | None = None, media_type: str | None = None,
    api_key: str | None = None, client=None,
) -> tuple[MealEstimate, str]:
    if client is None:
        # pick_backend, nie goły LLM_BACKEND: w auto z VERTEX_PROJECT i kluczem w env
        # klient bez tego cicho spadłby z Vertex na klucz API.
        client = gemini_client("vertex" if pick_backend(api_key) == "vertex" else "gemini", api_key)
    from google.genai import types

    contents: list = []
    if image_bytes is not None:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=media_type))
    contents.append(prompt)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=MealEstimate,
    )

    last_exc: Exception = RuntimeError("Brak modeli Gemini do wypróbowania (GEMINI_MODELS).")
    deadline = time.monotonic() + TOTAL_DEADLINE_S
    for model in GEMINI_MODELS:
        if time.monotonic() > deadline:
            logger.warning("Gemini: przekroczono łączny limit %s s — przerywam kaskadę.",
                           TOTAL_DEADLINE_S)
            break
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            estimate = response.parsed
            if estimate is None:
                raise RuntimeError(f"Nie udało się sparsować odpowiedzi modelu Gemini ({model}).")
        except Exception as exc:
            last_exc = exc
            logger.info("Gemini: model %s niedostępny (%s) — próbuję następny z kaskady.",
                        model, crypto.scrub(str(exc)))
            continue
        return estimate, model
    raise last_exc
