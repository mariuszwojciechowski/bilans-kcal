"""Moduł M6: zapotrzebowanie na makroskładniki wg norm WHO i ocena pokrycia.

Normy nie są zaszyte w kodzie — leżą w app/resources/who_norms.json (z metadanymi
źródeł) i są rozwiązywane per użytkownik: grupa wiekowa z wieku, ewentualne
nadpisania per płeć, białko z masy ciała, udziały energii z energii docelowej
(ta z kolei jest per użytkownik: BMR wg płci/wieku/wzrostu/wagi + cel deficytu).
Zmiana użytkownika = inne wartości bez zmiany kodu."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_FAT = 9
KCAL_PER_G_CARBS = 4

NORMS_PATH = Path(__file__).resolve().parent.parent / "resources" / "who_norms.json"


@lru_cache(maxsize=1)
def _norms() -> dict:
    return json.loads(NORMS_PATH.read_text())


def resolve_norms(sex: str, age: int) -> dict:
    """Wartości norm dla konkretnego profilu: grupa wg wieku + nadpisania per płeć.
    Wiek poniżej najniższej grupy (aplikacja jest dla dorosłych) -> grupa 'adult'."""
    data = _norms()
    groups = data["groups"]
    chosen = None
    for g in groups:
        m = g.get("match", {})
        if age >= m.get("age_min", 0) and age <= m.get("age_max", 200):
            chosen = g
            break
    if chosen is None:
        chosen = next(g for g in groups if g["id"] == "adult")
    resolved = {k: v for k, v in chosen.items() if k not in ("id", "match", "note")}
    resolved.update(data.get("sex_overrides", {}).get(sex.upper(), {}))
    resolved["group_id"] = chosen["id"]
    return resolved


@dataclass
class MacroRange:
    name: str
    min_g: float
    max_g: float | None  # None = brak górnej granicy

    def status(self, consumed_g: float) -> str:
        if consumed_g < self.min_g:
            return "below"
        if self.max_g is not None and consumed_g > self.max_g:
            return "above"
        return "ok"


@dataclass
class MacroTargets:
    protein: MacroRange
    protein_cut: MacroRange
    fat: MacroRange
    carbs: MacroRange
    sugars_max_g: float
    fiber_min_g: float
    group_id: str


def who_targets(e_target_kcal: float, weight_kg: float, sex: str = "M", age: int = 40) -> MacroTargets:
    n = resolve_norms(sex, age)
    return MacroTargets(
        protein=MacroRange("protein", n["protein_g_per_kg_min"] * weight_kg, None),
        protein_cut=MacroRange(
            "protein_cut",
            n["protein_cut_g_per_kg"][0] * weight_kg,
            n["protein_cut_g_per_kg"][1] * weight_kg,
        ),
        fat=MacroRange(
            "fat",
            n["fat_energy"][0] * e_target_kcal / KCAL_PER_G_FAT,
            n["fat_energy"][1] * e_target_kcal / KCAL_PER_G_FAT,
        ),
        carbs=MacroRange(
            "carbs",
            n["carbs_energy"][0] * e_target_kcal / KCAL_PER_G_CARBS,
            n["carbs_energy"][1] * e_target_kcal / KCAL_PER_G_CARBS,
        ),
        sugars_max_g=n["free_sugars_energy_max"] * e_target_kcal / KCAL_PER_G_CARBS,
        fiber_min_g=n["fiber_g_min"],
        group_id=n["group_id"],
    )


def coverage(targets: MacroTargets, protein_g: float, fat_g: float, carbs_g: float,
             fiber_g: float, sugars_g: float) -> dict:
    return {
        "group": targets.group_id,
        "protein": {
            "consumed_g": round(protein_g, 1),
            "who_min_g": round(targets.protein.min_g, 1),
            "cut_range_g": [round(targets.protein_cut.min_g, 1), round(targets.protein_cut.max_g, 1)],
            "status": targets.protein.status(protein_g),
        },
        "fat": {
            "consumed_g": round(fat_g, 1),
            "range_g": [round(targets.fat.min_g, 1), round(targets.fat.max_g, 1)],
            "status": targets.fat.status(fat_g),
        },
        "carbs": {
            "consumed_g": round(carbs_g, 1),
            "range_g": [round(targets.carbs.min_g, 1), round(targets.carbs.max_g, 1)],
            "status": targets.carbs.status(carbs_g),
        },
        "fiber": {
            "consumed_g": round(fiber_g, 1),
            "min_g": targets.fiber_min_g,
            "status": "ok" if fiber_g >= targets.fiber_min_g else "below",
        },
        "sugars": {
            "consumed_g": round(sugars_g, 1),
            "max_g": round(targets.sugars_max_g, 1),
            "status": "ok" if sugars_g <= targets.sugars_max_g else "above",
        },
    }
