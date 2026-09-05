"""Model energetyczny: BMR (Mifflin-St Jeor), NEAT z kroków, MET dla aktywności,
teoretyczne TDEE. Pomiar Garmina pozostaje źródłem prawdy do bilansu — ten moduł
liczy wartości teoretyczne (prognoza, sanity-check, fallback).

Współczynniki MET/kroki/dystans mieszkają w app/resources/met_table.json
(WYMAGANIA.md §4: „Tabela MET konfigurowalna"), wzorem norm WHO w
`macros.py`/`who_norms.json` — plik jest jedynym źródłem prawdy, brak pliku
jest błędem (ładowany eagerly przy imporcie tego modułu), nie cichym
fallbackiem na wartości w kodzie."""

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

MET_PATH = Path(__file__).resolve().parent.parent / "resources" / "met_table.json"


@lru_cache(maxsize=1)
def _met() -> dict:
    return json.loads(MET_PATH.read_text())


def age_years(birth_date: date, on_date: date) -> int:
    """Funkcja pomocnicza (dokładna data). Profil operuje na roku — patrz age_from_year."""
    years = on_date.year - birth_date.year
    if (on_date.month, on_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def age_from_year(birth_year: int, on_date: date) -> int:
    """Wiek z konwencji „środek roku" (jakby każdy rodził się 1 lipca) — błąd
    ≤ 1 rok, bez systematycznego przesunięcia w żadną stronę."""
    return on_date.year - birth_year - (0 if (on_date.month, on_date.day) >= (7, 1) else 1)


def bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    s = 5 if sex.upper() == "M" else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + s


def smoothed_weight(weights: list[tuple[date, float]], window_days: int = 7) -> float | None:
    """Średnia z pomiarów z ostatnich `window_days` dni (licząc od najnowszego pomiaru).
    Waga dobowa fluktuuje ±1-2 kg — pojedynczy pomiar jest mylący."""
    if not weights:
        return None
    weights = sorted(weights, key=lambda w: w[0])
    newest = weights[-1][0]
    recent = [kg for d, kg in weights if (newest - d).days < window_days]
    return sum(recent) / len(recent)


# Stałe czytane z pliku przy KAŻDYM wywołaniu (przez `_met()`, cache'owany —
# tani odczyt) — nie eager module-level, żeby podmiana `MET_PATH` +
# `_met.cache_clear()` (test `test_met_table.py`) naprawdę zmieniała wynik.
# Wyjątek: `DEFAULT_STEPS` niżej, bo trzy inne moduły importują go po nazwie.
def _cycling_thresholds() -> list[tuple[float, float]]:
    return [
        (float("inf") if limit is None else limit, met)
        for limit, met in _met()["cycling"]["met_by_speed_kmh"]
    ]


def neat_from_steps(steps: int, weight_kg: float, activity_steps: int = 0) -> float:
    """Kcal z kroków poza zarejestrowanymi aktywnościami (bez podwójnego liczenia)."""
    effective = max(steps - activity_steps, 0)
    return effective * weight_kg * _met()["steps"]["kcal_per_step_per_kg"]


def running_kcal(weight_kg: float, distance_m: float) -> float:
    # netto ~0.9-1.0 kcal / kg / km; używamy 1.0 brutto
    return weight_kg * (distance_m / 1000.0) * _met()["distance"]["running_kcal_per_kg_per_km"]


def cycling_met(distance_m: float | None, duration_s: int) -> float:
    if not distance_m or duration_s <= 0:
        return 8.0
    speed_kmh = (distance_m / 1000.0) / (duration_s / 3600.0)
    for limit, met in _cycling_thresholds():
        if speed_kmh < limit:
            return met
    return _met()["garmin_activities"]["default_met"]


def activity_kcal_model(
    activity_type: str,
    duration_s: int,
    distance_m: float | None,
    weight_kg: float,
) -> float:
    """Teoretyczne kcal aktywności, **netto** (bez spoczynku — BMR liczony
    osobno, patrz `tdee_theoretical`). Typy wg typeKey Garmina."""
    t = activity_type.lower()
    hours = duration_s / 3600.0
    ga = _met()["garmin_activities"]
    if "running" in t or t == "run":
        return running_kcal(weight_kg, distance_m or 0)
    if "cycling" in t or "biking" in t:
        return (cycling_met(distance_m, duration_s) - 1) * weight_kg * hours
    if "hiking" in t:
        return (ga["hiking_met"] - 1) * weight_kg * hours
    if "walking" in t:
        return (ga["walking_met"] - 1) * weight_kg * hours
    if "strength" in t or "training" in t:
        return (ga["strength_training_met"] - 1) * weight_kg * hours
    return (ga["default_met"] - 1) * weight_kg * hours


@dataclass
class TheoreticalTdee:
    bmr: float
    neat: float
    activities: float
    tef: float

    @property
    def total(self) -> float:
        return self.bmr + self.neat + self.activities + self.tef


def tdee_theoretical(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: str,
    steps: int,
    activities: list[dict],
    kcal_in: float = 0,
) -> TheoreticalTdee:
    """activities: [{"type", "duration_s", "distance_m", "kcal_net"?, "steps"?}].
    Kcal aktywności są netto, BMR liczone osobno. `kcal_net`, gdy podany (np.
    z pomiaru zegarka po odjęciu spoczynku), wygrywa nad modelem MET; `steps`,
    gdy podany, wygrywa nad przybliżeniem z dystansu.
    TEF (termogeneza poposiłkowa) ~10% spożycia — 0, gdy brak wpisów posiłków."""
    bmr = bmr_mifflin(weight_kg, height_cm, age, sex)
    act_kcal = sum(
        a.get(
            "kcal_net",
            activity_kcal_model(a["type"], a["duration_s"], a.get("distance_m"), weight_kg),
        )
        for a in activities
    )
    # kroki wykonane w ramach aktywności: z zegarka, gdy jest; inaczej przybliżenie
    # z dystansu — bieg/chód ~1400 kroków/km
    activity_steps = int(
        sum(
            a["steps"] if a.get("steps") is not None else (
                (a.get("distance_m") or 0) / 1000.0 * _met()["steps"]["steps_per_km"]
                if "running" in a["type"].lower() or "walking" in a["type"].lower()
                else 0
            )
            for a in activities
        )
    )
    neat = neat_from_steps(steps, weight_kg, activity_steps)
    tef = 0.10 * kcal_in
    return TheoreticalTdee(bmr=bmr, neat=neat, activities=act_kcal, tef=tef)


# Jedyna stała importowana po nazwie spoza tego modułu (app/routers/day.py,
# tests/test_activities_api.py, tests/test_queue_settings.py) — zostaje
# eager, żeby `from app.services.energy import DEFAULT_STEPS` działało bez zmian.
DEFAULT_STEPS = _met()["steps"]["default_steps"]


def manual_activity_kcal(activity_type: str, intensity: str, duration_s: int,
                         distance_m: float | None, weight_kg: float) -> tuple[float, str]:
    """Oblicza kcal dla ręcznej aktywności. Zwraca (kcal, wyjaśnienie)."""
    manual = _met()["manual"]
    intensity_idx = {name: idx for idx, name in enumerate(manual["intensity_order"])}.get(intensity, 1)
    duration_h = duration_s / 3600.0

    if activity_type == "running":
        if distance_m:
            kcal = weight_kg * (distance_m / 1000.0) * _met()["distance"]["running_kcal_per_kg_per_km"]
            explanation = f"bieg {distance_m/1000:.1f} km × {weight_kg:.0f} kg"
        else:
            met = manual["types"][activity_type][intensity_idx]
            kcal = met * weight_kg * duration_h
            explanation = f"MET {met} × {weight_kg:.0f} kg × {duration_h:.2f} h"
    elif activity_type == "cycling":
        met = manual["types"][activity_type][intensity_idx]
        kcal = met * weight_kg * duration_h
        explanation = f"MET {met} × {weight_kg:.0f} kg × {duration_h:.2f} h"
    elif activity_type == "walking":
        if distance_m:
            walking_per_km = _met()["distance"]["walking_kcal_per_kg_per_km"]
            kcal = walking_per_km * weight_kg * (distance_m / 1000.0)
            explanation = f"marsz {distance_m/1000:.1f} km × {weight_kg:.0f} kg × {walking_per_km}"
        else:
            met = manual["types"][activity_type][intensity_idx]
            kcal = met * weight_kg * duration_h
            explanation = f"MET {met} × {weight_kg:.0f} kg × {duration_h:.2f} h"
    elif activity_type == "strength_training":
        met = manual["types"][activity_type][intensity_idx]
        kcal = met * weight_kg * duration_h
        explanation = f"MET {met} × {weight_kg:.0f} kg × {duration_h:.2f} h"
    elif activity_type == "swimming":
        met = manual["types"][activity_type][intensity_idx]
        kcal = met * weight_kg * duration_h
        explanation = f"MET {met} × {weight_kg:.0f} kg × {duration_h:.2f} h"
    else:
        kcal = 0
        explanation = "nieznana aktywność"

    return round(kcal), explanation
