"""Moduł M4: szacowanie kcal i makroskładników posiłku ze zdjęcia (lub opisu tekstowego)
przez model wizyjny LLM. Model samodzielnie identyfikuje składniki, masy i wartości
odżywcze (bez zewnętrznej bazy żywieniowej — decyzja D6). Wynik zawsze z przedziałem
kcal_min–kcal_max i listą założeń do weryfikacji przez użytkownika.

Backend wymienny (FIT_KRASNAL_LLM = auto | claude | gemini):
- claude — Anthropic API (ANTHROPIC_API_KEY),
- gemini — Google AI Studio (GEMINI_API_KEY / GOOGLE_API_KEY; ma darmowy tier).
W trybie auto wybierany jest gemini, jeśli jego klucz jest ustawiony, inaczej claude."""

import base64
import os
from typing import Literal

from pydantic import BaseModel, Field

from ..config import GEMINI_MODEL, LLM_BACKEND, VISION_MODEL

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


def _gemini_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def pick_backend() -> str:
    if LLM_BACKEND in ("claude", "gemini"):
        return LLM_BACKEND
    return "gemini" if _gemini_key() else "claude"


# ── Publiczne API ─────────────────────────────────────────────────────────

def estimate_from_photo(image_bytes: bytes, ext: str, note: str | None = None) -> MealEstimate:
    media_type = MEDIA_TYPES.get(ext.lower().lstrip("."))
    if media_type is None:
        raise ValueError(f"Nieobsługiwany format zdjęcia: {ext}")
    prompt = "Oszacuj wartości odżywcze posiłku ze zdjęcia." + (
        f" Uwaga użytkownika: {note}" if note else ""
    )
    if pick_backend() == "gemini":
        return _estimate_gemini(prompt, image_bytes, media_type)
    return _estimate_claude(prompt, image_bytes, media_type)


def estimate_from_text(description: str) -> MealEstimate:
    prompt = f"Oszacuj wartości odżywcze posiłku: {description}"
    if pick_backend() == "gemini":
        return _estimate_gemini(prompt)
    return _estimate_claude(prompt)


# ── Backend: Claude (Anthropic API) ───────────────────────────────────────

def _estimate_claude(
    prompt: str, image_bytes: bytes | None = None, media_type: str | None = None
) -> MealEstimate:
    import anthropic

    try:
        client = anthropic.Anthropic()
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
    return estimate


# ── Backend: Gemini (Google AI Studio, darmowy tier) ──────────────────────

def _estimate_gemini(
    prompt: str, image_bytes: bytes | None = None, media_type: str | None = None
) -> MealEstimate:
    if not _gemini_key():
        raise MealVisionNotConfigured(
            "Brak klucza Gemini — ustaw GEMINI_API_KEY (darmowy klucz: aistudio.google.com)."
        )
    from google import genai
    from google.genai import types

    client = genai.Client()
    contents: list = []
    if image_bytes is not None:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=media_type))
    contents.append(prompt)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=MealEstimate,
        ),
    )
    estimate = response.parsed
    if estimate is None:
        raise RuntimeError("Nie udało się sparsować odpowiedzi modelu Gemini.")
    return estimate
