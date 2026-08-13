"""Moduł M4: szacowanie kcal i makroskładników posiłku ze zdjęcia (lub opisu tekstowego)
przez model wizyjny Claude. Model samodzielnie identyfikuje składniki, masy i wartości
odżywcze (bez zewnętrznej bazy żywieniowej — decyzja D6). Wynik zawsze z przedziałem
kcal_min–kcal_max i listą założeń do weryfikacji przez użytkownika."""

import base64
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from ..config import VISION_MODEL

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


def _client() -> anthropic.Anthropic:
    try:
        client = anthropic.Anthropic()
        client._validate_headers({}, {})  # wymusza rozwiązanie uwierzytelnienia
    except TypeError as exc:
        raise MealVisionNotConfigured(
            "Brak klucza Claude API — ustaw zmienną ANTHROPIC_API_KEY (patrz .env.example)."
        ) from exc
    return client


def estimate_from_photo(image_bytes: bytes, ext: str, note: str | None = None) -> MealEstimate:
    media_type = MEDIA_TYPES.get(ext.lower().lstrip("."))
    if media_type is None:
        raise ValueError(f"Nieobsługiwany format zdjęcia: {ext}")
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(image_bytes).decode(),
            },
        },
        {
            "type": "text",
            "text": "Oszacuj wartości odżywcze posiłku ze zdjęcia."
            + (f" Uwaga użytkownika: {note}" if note else ""),
        },
    ]
    return _estimate(content)


def estimate_from_text(description: str) -> MealEstimate:
    return _estimate(
        [{"type": "text", "text": f"Oszacuj wartości odżywcze posiłku: {description}"}]
    )


def _estimate(content: list[dict]) -> MealEstimate:
    response = _client().messages.parse(
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
