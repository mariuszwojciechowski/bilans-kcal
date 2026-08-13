"""Moduł M6: zapotrzebowanie na makroskładniki wg norm WHO/FAO (cele populacyjne)
liczone od energii docelowej (zapotrzebowanie + cel deficytu), oraz ocena pokrycia."""

from dataclasses import dataclass

KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_FAT = 9
KCAL_PER_G_CARBS = 4

WHO_PROTEIN_G_PER_KG = 0.83          # bezpieczne spożycie
CUT_PROTEIN_G_PER_KG = (1.2, 1.6)    # cel redukcyjny (ponad normę WHO, ochrona mięśni)
WHO_FAT_ENERGY = (0.15, 0.30)
WHO_CARBS_ENERGY = (0.55, 0.75)
WHO_FREE_SUGARS_ENERGY_MAX = 0.10
WHO_FIBER_G_MIN = 25.0


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


def who_targets(e_target_kcal: float, weight_kg: float) -> MacroTargets:
    return MacroTargets(
        protein=MacroRange("protein", WHO_PROTEIN_G_PER_KG * weight_kg, None),
        protein_cut=MacroRange(
            "protein_cut",
            CUT_PROTEIN_G_PER_KG[0] * weight_kg,
            CUT_PROTEIN_G_PER_KG[1] * weight_kg,
        ),
        fat=MacroRange(
            "fat",
            WHO_FAT_ENERGY[0] * e_target_kcal / KCAL_PER_G_FAT,
            WHO_FAT_ENERGY[1] * e_target_kcal / KCAL_PER_G_FAT,
        ),
        carbs=MacroRange(
            "carbs",
            WHO_CARBS_ENERGY[0] * e_target_kcal / KCAL_PER_G_CARBS,
            WHO_CARBS_ENERGY[1] * e_target_kcal / KCAL_PER_G_CARBS,
        ),
        sugars_max_g=WHO_FREE_SUGARS_ENERGY_MAX * e_target_kcal / KCAL_PER_G_CARBS,
        fiber_min_g=WHO_FIBER_G_MIN,
    )


def coverage(targets: MacroTargets, protein_g: float, fat_g: float, carbs_g: float,
             fiber_g: float, sugars_g: float) -> dict:
    return {
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
