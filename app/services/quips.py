"""Żartobliwe teksty krasnala do panelu 'Dodaj posiłek' — dobierane do sytuacji dnia.

Priorytet kategorii dnia: przekroczony cukier > za mało białka > za mało błonnika
> nadwyżka kcal > wyraźne niedojadanie > w normie (pusty dziennik osobno).

Różnorodność (właściciel 2026-09-06 — „ciągle losują się podobne"):
- do puli wchodzą DWIE pierwsze pasujące kategorie dnia, nie jedna, plus
  kategoria dystansu do celu wagi (osiągnięty cel zawsze wygrywa sam);
- losowanie jest ważone wielkością puli: każdy tekst ma równą szansę, więc
  5-tekstowa kategoria celu nie zjada 50% losowań;
- pamięć ostatnich RECENT_MEMORY tekstów per użytkownik (w pamięci procesu,
  jak throttle synchronizacji) — wykluczane z losowania, dopóki pula ma z czego
  wybierać. Nie przeżywa restartu procesu i to jest OK.
"""

import json
import random
from collections import deque
from functools import lru_cache
from pathlib import Path

QUIPS_PATH = Path(__file__).resolve().parent.parent / "resources" / "quips.json"

RECENT_MEMORY = 10          # tyle ostatnio pokazanych tekstów nie wraca (per użytkownik)
DAY_CATEGORIES_IN_POOL = 2  # ile pasujących kategorii dnia wchodzi do puli

_recent: dict[int | None, deque] = {}


@lru_cache(maxsize=1)
def _quips() -> dict:
    data = json.loads(QUIPS_PATH.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def day_categories(kcal_in: float, e_target: float, balance: float, macros: dict) -> list[str]:
    """Wszystkie pasujące kategorie dnia w kolejności priorytetu; pierwsza to
    dotychczasowy wynik `pick_category`."""
    if kcal_in == 0:
        return ["empty"]
    cats: list[str] = []
    if macros["sugars"]["status"] == "above":
        cats.append("sugar_high")
    ratio = kcal_in / e_target if e_target > 0 else 0
    if macros["protein"]["status"] == "below" and ratio > 0.6:
        cats.append("protein_low")
    if macros["fiber"]["status"] == "below" and ratio > 0.7:
        cats.append("fiber_low")
    if balance > 0:
        cats.append("over")
    elif ratio < 0.45:
        cats.append("under")
    else:
        cats.append("ontrack")
    return cats


def pick_category(kcal_in: float, e_target: float, balance: float, macros: dict) -> str:
    return day_categories(kcal_in, e_target, balance, macros)[0]


def goal_category(weight_to_goal_kg: float) -> str:
    if weight_to_goal_kg <= 0:
        return "goal_reached"
    if weight_to_goal_kg <= 2:
        return "goal_close"
    return "goal_far"


def candidate_categories(kcal_in: float, e_target: float, balance: float, macros: dict,
                         weight_to_goal_kg: float | None = None) -> list[str]:
    """Kategorie, z których składa się pula do losowania."""
    cats = day_categories(kcal_in, e_target, balance, macros)[:DAY_CATEGORIES_IN_POOL]
    if weight_to_goal_kg is not None:
        goal_cat = goal_category(weight_to_goal_kg)
        if goal_cat == "goal_reached":
            return [goal_cat]
        cats.append(goal_cat)
    return cats


def pick(kcal_in: float, e_target: float, balance: float, macros: dict,
         weight_to_goal_kg: float | None = None, user_id: int | None = None) -> str:
    """Losuje tekst z połączonej puli kategorii (równa szansa per tekst),
    omijając ostatnie RECENT_MEMORY tekstów pokazanych temu użytkownikowi.
    Losowanie odbywa się przy każdym renderze dashboardu."""
    quips = _quips()
    pool = [t for cat in candidate_categories(kcal_in, e_target, balance, macros,
                                              weight_to_goal_kg) for t in quips[cat]]
    recent = _recent.setdefault(user_id, deque(maxlen=RECENT_MEMORY))
    fresh = [t for t in pool if t not in recent] or pool
    text = random.choice(fresh)
    recent.append(text)
    diff = f"{max(weight_to_goal_kg, 0):.1f}" if weight_to_goal_kg is not None else "?"
    return text.replace("{diff}", diff)
