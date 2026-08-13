"""Model energetyczny: BMR (Mifflin-St Jeor), NEAT z kroków, MET dla aktywności,
teoretyczne TDEE. Pomiar Garmina pozostaje źródłem prawdy do bilansu — ten moduł
liczy wartości teoretyczne (prognoza, sanity-check, fallback)."""

from dataclasses import dataclass
from datetime import date


def age_years(birth_date: date, on_date: date) -> int:
    years = on_date.year - birth_date.year
    if (on_date.month, on_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


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


# kcal na krok na kg masy ciała (chód ~0.57 kcal/kg na 1000 kroków)
KCAL_PER_STEP_PER_KG = 0.00057

# MET wg Compendium of Physical Activities (uproszczone)
MET_STRENGTH = 4.0
MET_CYCLING_BY_SPEED_KMH = [(16.0, 6.0), (20.0, 8.0), (float("inf"), 10.0)]
MET_DEFAULT = 5.0


def neat_from_steps(steps: int, weight_kg: float, activity_steps: int = 0) -> float:
    """Kcal z kroków poza zarejestrowanymi aktywnościami (bez podwójnego liczenia)."""
    effective = max(steps - activity_steps, 0)
    return effective * weight_kg * KCAL_PER_STEP_PER_KG


def running_kcal(weight_kg: float, distance_m: float) -> float:
    # netto ~0.9-1.0 kcal / kg / km; używamy 1.0 brutto
    return weight_kg * (distance_m / 1000.0)


def cycling_met(distance_m: float | None, duration_s: int) -> float:
    if not distance_m or duration_s <= 0:
        return 8.0
    speed_kmh = (distance_m / 1000.0) / (duration_s / 3600.0)
    for limit, met in MET_CYCLING_BY_SPEED_KMH:
        if speed_kmh < limit:
            return met
    return MET_DEFAULT


def activity_kcal_model(
    activity_type: str,
    duration_s: int,
    distance_m: float | None,
    weight_kg: float,
) -> float:
    """Teoretyczne kcal aktywności. Typy wg typeKey Garmina."""
    t = activity_type.lower()
    hours = duration_s / 3600.0
    if "running" in t or t == "run":
        return running_kcal(weight_kg, distance_m or 0)
    if "cycling" in t or "biking" in t:
        return cycling_met(distance_m, duration_s) * weight_kg * hours
    if "strength" in t or "training" in t:
        return MET_STRENGTH * weight_kg * hours
    return MET_DEFAULT * weight_kg * hours


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
    """activities: [{"type", "duration_s", "distance_m"}].
    TEF (termogeneza poposiłkowa) ~10% spożycia — 0, gdy brak wpisów posiłków."""
    bmr = bmr_mifflin(weight_kg, height_cm, age, sex)
    act_kcal = sum(
        activity_kcal_model(a["type"], a["duration_s"], a.get("distance_m"), weight_kg)
        for a in activities
    )
    # kroki wykonane w ramach aktywności: przybliżenie — bieg/chód ~1400 kroków/km
    activity_steps = int(
        sum(
            (a.get("distance_m") or 0) / 1000.0 * 1400
            for a in activities
            if "running" in a["type"].lower() or "walking" in a["type"].lower()
        )
    )
    neat = neat_from_steps(steps, weight_kg, activity_steps)
    tef = 0.10 * kcal_in
    return TheoreticalTdee(bmr=bmr, neat=neat, activities=act_kcal, tef=tef)
