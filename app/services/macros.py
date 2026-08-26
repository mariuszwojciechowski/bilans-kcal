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


DEFAULT_LIFESTYLE = "active"


def resolve_norms(sex: str, age: int, lifestyle: str = DEFAULT_LIFESTYLE) -> dict:
    """Wartości norm dla konkretnego profilu: grupa wg wieku + nadpisania per płeć
    + zakres białka wg stylu życia (senior podbija dolną/górną granicę do floora
    PROT-AGE). Wiek poniżej najniższej grupy -> grupa 'adult'."""
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

    styles = data.get("lifestyles", {})
    style = styles.get(lifestyle) or styles[DEFAULT_LIFESTYLE]
    lo, hi = style["protein_g_per_kg"]
    if chosen["id"] == "senior":
        floor_lo, floor_hi = data.get("senior_protein_floor", [1.0, 1.2])
        lo, hi = max(lo, floor_lo), max(hi, floor_hi)
    resolved["protein_range_g_per_kg"] = [lo, hi]
    # trenujący: węgle w g/kg (ACSM/ISSN), tłuszcze 20-35%E; inaczej zakresy WHO %E
    resolved["carbs_g_per_kg"] = style.get("carbs_g_per_kg")
    if style.get("fat_energy"):
        resolved["fat_energy"] = style["fat_energy"]
    resolved["lifestyle_label"] = style["label"]
    resolved["lifestyle_id"] = lifestyle if lifestyle in styles else DEFAULT_LIFESTYLE
    return resolved


def lifestyle_options() -> dict[str, str]:
    return {k: v["label"] for k, v in _norms().get("lifestyles", {}).items()}


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
    protein_who_min_g: float          # bezpieczne minimum WHO (0.83 g/kg)
    protein: MacroRange               # zakres wg stylu życia — do oceny statusu
    fat: MacroRange
    carbs: MacroRange
    sugars_max_g: float
    fiber_min_g: float
    group_id: str
    lifestyle_label: str


def who_targets(e_target_kcal: float, weight_kg: float, sex: str = "M", age: int = 40,
                lifestyle: str = DEFAULT_LIFESTYLE) -> MacroTargets:
    n = resolve_norms(sex, age, lifestyle)
    p_lo, p_hi = n["protein_range_g_per_kg"]
    return MacroTargets(
        protein_who_min_g=n["protein_g_per_kg_min"] * weight_kg,
        protein=MacroRange("protein", p_lo * weight_kg, p_hi * weight_kg),
        fat=MacroRange(
            "fat",
            n["fat_energy"][0] * e_target_kcal / KCAL_PER_G_FAT,
            n["fat_energy"][1] * e_target_kcal / KCAL_PER_G_FAT,
        ),
        carbs=(
            MacroRange("carbs", n["carbs_g_per_kg"][0] * weight_kg,
                       n["carbs_g_per_kg"][1] * weight_kg)
            if n.get("carbs_g_per_kg")
            else MacroRange(
                "carbs",
                n["carbs_energy"][0] * e_target_kcal / KCAL_PER_G_CARBS,
                n["carbs_energy"][1] * e_target_kcal / KCAL_PER_G_CARBS,
            )
        ),
        sugars_max_g=n["free_sugars_energy_max"] * e_target_kcal / KCAL_PER_G_CARBS,
        fiber_min_g=n["fiber_g_min"],
        group_id=n["group_id"],
        lifestyle_label=n["lifestyle_label"],
    )


def bar_pct(consumed_g: float, b1: float, b2: float, b3: float) -> float:
    """Pozycja na pasku [0, 100] wg trzech punktów odniesienia.

    0 -> 0%, b1 -> 1/3, b2 -> 2/3, b3 -> 100%. W każdej z trzech sekcji
    (0-b1, b1-b2, b2-b3) postęp jest liniowy względem długości TEJ sekcji
    (nie całego paska). Dla białka/węglowodanów/tłuszczów b1/b2 to dolna/
    górna granica normy i b3 = 3x górna granica; dla błonnika (tylko dolna
    granica) b1/b2/b3 = 1x/2x/3x minimum; dla cukrów wolnych (tylko górna
    granica) b1/b2/b3 = 1x/2x/3x maksimum."""
    if b3 <= 0 or consumed_g <= 0:
        return 0.0
    if consumed_g <= b1:
        pct = (consumed_g / b1) / 3 if b1 > 0 else 0.0
    elif consumed_g <= b2:
        pct = 1 / 3 + ((consumed_g - b1) / (b2 - b1)) / 3 if b2 > b1 else 2 / 3
    else:
        pct = 2 / 3 + min(1.0, (consumed_g - b2) / (b3 - b2)) / 3 if b3 > b2 else 1.0
    return round(min(100.0, pct * 100), 1)


def coverage(targets: MacroTargets, protein_g: float, fat_g: float, carbs_g: float,
             fiber_g: float, sugars_g: float) -> dict:
    return {
        "group": targets.group_id,
        "lifestyle": targets.lifestyle_label,
        "protein": {
            "consumed_g": round(protein_g, 1),
            "who_min_g": round(targets.protein_who_min_g, 1),
            "range_g": [round(targets.protein.min_g, 1), round(targets.protein.max_g, 1)],
            "status": targets.protein.status(protein_g),
            "bar_pct": bar_pct(protein_g, targets.protein.min_g, targets.protein.max_g,
                                3 * targets.protein.max_g),
        },
        "fat": {
            "consumed_g": round(fat_g, 1),
            "range_g": [round(targets.fat.min_g, 1), round(targets.fat.max_g, 1)],
            "status": targets.fat.status(fat_g),
            "bar_pct": bar_pct(fat_g, targets.fat.min_g, targets.fat.max_g,
                                3 * targets.fat.max_g),
        },
        "carbs": {
            "consumed_g": round(carbs_g, 1),
            "range_g": [round(targets.carbs.min_g, 1), round(targets.carbs.max_g, 1)],
            "status": targets.carbs.status(carbs_g),
            "bar_pct": bar_pct(carbs_g, targets.carbs.min_g, targets.carbs.max_g,
                                3 * targets.carbs.max_g),
        },
        "fiber": {
            "consumed_g": round(fiber_g, 1),
            "min_g": targets.fiber_min_g,
            "status": "ok" if fiber_g >= targets.fiber_min_g else "below",
            "bar_pct": bar_pct(fiber_g, targets.fiber_min_g, 2 * targets.fiber_min_g,
                                3 * targets.fiber_min_g),
        },
        "sugars": {
            "consumed_g": round(sugars_g, 1),
            "max_g": round(targets.sugars_max_g, 1),
            "status": "ok" if sugars_g <= targets.sugars_max_g else "above",
            "bar_pct": bar_pct(sugars_g, targets.sugars_max_g, 2 * targets.sugars_max_g,
                                3 * targets.sugars_max_g),
        },
    }
