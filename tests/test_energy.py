from datetime import date

from app.services.energy import (
    activity_kcal_model,
    age_from_year,
    age_years,
    bmr_mifflin,
    cycling_met,
    neat_from_steps,
    smoothed_weight,
    tdee_theoretical,
)


def test_bmr_mifflin_male():
    # 90 kg, 180 cm, 45 lat: 900 + 1125 - 225 + 5 = 1805
    assert bmr_mifflin(90, 180, 45, "M") == 1805


def test_bmr_mifflin_female():
    # 70 kg, 165 cm, 30 lat: 700 + 1031.25 - 150 - 161 = 1420.25
    assert bmr_mifflin(70, 165, 30, "F") == 1420.25


def test_age_years_before_and_after_birthday():
    birth = date(1980, 6, 15)
    assert age_years(birth, date(2026, 6, 14)) == 45
    assert age_years(birth, date(2026, 6, 15)) == 46


def test_age_from_year_midyear_convention():
    # 1985: przed 1 lipca jeszcze "40", od 1 lipca już "41" (rok bieżący 2026)
    assert age_from_year(1985, date(2026, 6, 30)) == 40
    assert age_from_year(1985, date(2026, 7, 1)) == 41


def test_age_from_year_close_to_birth_date_age():
    # różnica wieku z roku vs. z pełnej daty urodzenia ≤ 1 rok dla tej samej osoby
    birth = date(1985, 3, 20)
    on = date(2026, 8, 1)
    assert abs(age_from_year(1985, on) - age_years(birth, on)) <= 1


def test_bmr_diff_year_vs_full_date_is_small():
    birth = date(1985, 3, 20)
    on = date(2026, 8, 1)
    bmr_full = bmr_mifflin(80, 175, age_years(birth, on), "M")
    bmr_year = bmr_mifflin(80, 175, age_from_year(1985, on), "M")
    assert abs(bmr_full - bmr_year) <= 5


def test_smoothed_weight_window():
    weights = [(date(2026, 8, d), float(w)) for d, w in [(1, 92), (5, 91), (10, 90), (12, 89)]]
    # okno 7 dni od najnowszego pomiaru (12.08): 10.08 i 12.08
    assert smoothed_weight(weights) == 89.5


def test_smoothed_weight_empty():
    assert smoothed_weight([]) is None


def test_neat_subtracts_activity_steps():
    full = neat_from_steps(10000, 90)
    reduced = neat_from_steps(10000, 90, activity_steps=4000)
    assert full > reduced > 0
    assert reduced == 6000 * 90 * 0.00057


def test_running_kcal_by_distance():
    kcal = activity_kcal_model("running", duration_s=1800, distance_m=5000, weight_kg=90)
    assert kcal == 450  # 1.0 * 90 kg * 5 km


def test_cycling_met_scales_with_speed():
    # netto: (MET - 1) * kg * h — BMR liczony osobno (day.py)
    slow = activity_kcal_model("cycling", 3600, 15000, 90)   # 15 km/h -> MET 6
    fast = activity_kcal_model("cycling", 3600, 25000, 90)   # 25 km/h -> MET 8 (obniżone z 10)
    assert slow == (6 - 1) * 90
    assert fast == (8 - 1) * 90


def test_cycling_top_speed_met_lowered_to_8():
    # Garmin dla szybkiej jazdy wychodzi ~7-8 MET brutto, nie 10 (TODO.md)
    assert cycling_met(distance_m=25000, duration_s=3600) == 8.0


def test_strength_uses_met():
    kcal = activity_kcal_model("strength_training", 3600, None, 90)
    assert kcal == (4.0 - 1) * 90


def test_walking_and_hiking_use_net_met():
    walking = activity_kcal_model("walking", 3600, None, 90)
    hiking = activity_kcal_model("hiking", 3600, None, 90)
    assert walking == (3.5 - 1) * 90
    assert hiking == (6.0 - 1) * 90


def test_hiking_checked_before_walking():
    # "hiking" nie zawiera "walking" ale test pilnuje, że gałąź hiking
    # rzeczywiście wygrywa dla tego typu (kolejność z TODO.md)
    assert activity_kcal_model("hiking", 3600, None, 90) != activity_kcal_model(
        "walking", 3600, None, 90
    )


def test_tdee_composition_and_tef():
    tdee = tdee_theoretical(
        weight_kg=90, height_cm=180, age=45, sex="M",
        steps=8000,
        activities=[{"type": "running", "duration_s": 1800, "distance_m": 5000}],
        kcal_in=2000,
    )
    assert tdee.bmr == 1805
    assert tdee.activities == 450
    assert tdee.tef == 200
    # kroki z biegu (5 km * 1400) odjęte od 8000
    assert tdee.neat == 1000 * 90 * 0.00057
    assert tdee.total == tdee.bmr + tdee.neat + tdee.activities + tdee.tef


def test_tdee_kcal_net_wins_over_model():
    tdee = tdee_theoretical(
        weight_kg=90, height_cm=180, age=45, sex="M", steps=8000,
        activities=[{"type": "walking", "duration_s": 3600, "distance_m": None,
                    "kcal_net": 250}],
        kcal_in=0,
    )
    assert tdee.activities == 250   # nie MET (3.5-1)*90=225


def test_tdee_steps_from_activity_wins_over_distance():
    tdee_with_steps = tdee_theoretical(
        weight_kg=90, height_cm=180, age=45, sex="M", steps=8000,
        activities=[{"type": "running", "duration_s": 1800, "distance_m": 5000, "steps": 6000}],
        kcal_in=0,
    )
    tdee_without_steps = tdee_theoretical(
        weight_kg=90, height_cm=180, age=45, sex="M", steps=8000,
        activities=[{"type": "running", "duration_s": 1800, "distance_m": 5000}],
        kcal_in=0,
    )
    # z jawnymi krokami (6000) odejmuje mniej niż z szacunku dystansu (7000) -> większy NEAT
    assert tdee_with_steps.neat > tdee_without_steps.neat
