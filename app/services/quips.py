"""Żartobliwe teksty krasnala do panelu 'Dodaj posiłek' — dobierane do sytuacji dnia.

Priorytet: przekroczony cukier > za mało białka > za mało błonnika > nadwyżka kcal
> wyraźne niedojadanie > pusty dziennik > w normie. Tekst losowany z kategorii."""

import json
import random
from functools import lru_cache
from pathlib import Path

QUIPS_PATH = Path(__file__).resolve().parent.parent / "resources" / "quips.json"


@lru_cache(maxsize=1)
def _quips() -> dict:
    data = json.loads(QUIPS_PATH.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def pick_category(kcal_in: float, e_target: float, balance: float, macros: dict) -> str:
    if kcal_in == 0:
        return "empty"
    if macros["sugars"]["status"] == "above":
        return "sugar_high"
    ratio = kcal_in / e_target if e_target > 0 else 0
    if macros["protein"]["status"] == "below" and ratio > 0.6:
        return "protein_low"
    if macros["fiber"]["status"] == "below" and ratio > 0.7:
        return "fiber_low"
    if balance > 0:
        return "over"
    if ratio < 0.45:
        return "under"
    return "ontrack"


def goal_category(weight_to_goal_kg: float) -> str:
    if weight_to_goal_kg <= 0:
        return "goal_reached"
    if weight_to_goal_kg <= 2:
        return "goal_close"
    return "goal_far"


def pick(kcal_in: float, e_target: float, balance: float, macros: dict,
         weight_to_goal_kg: float | None = None) -> str:
    """Losuje tekst: kategoria dnia albo — gdy ustawiono cel ciężaru — kategoria
    dystansu do celu (osiągnięty cel zawsze wygrywa). Losowanie odbywa się przy
    każdym renderze dashboardu, czyli w tych samych momentach co auto-sync."""
    candidates = [pick_category(kcal_in, e_target, balance, macros)]
    if weight_to_goal_kg is not None:
        goal_cat = goal_category(weight_to_goal_kg)
        if goal_cat == "goal_reached":
            candidates = [goal_cat]
        else:
            candidates.append(goal_cat)
    text = random.choice(_quips()[random.choice(candidates)])
    diff = f"{max(weight_to_goal_kg, 0):.1f}" if weight_to_goal_kg is not None else "?"
    return text.replace("{diff}", diff)
