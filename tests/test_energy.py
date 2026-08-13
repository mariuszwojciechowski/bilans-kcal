from datetime import date

from app.services.energy import (
    activity_kcal_model,
    age_years,
    bmr_mifflin,
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
    slow = activity_kcal_model("cycling", 3600, 15000, 90)   # 15 km/h -> MET 6
    fast = activity_kcal_model("cycling", 3600, 25000, 90)   # 25 km/h -> MET 10
    assert slow == 6 * 90
    assert fast == 10 * 90


def test_strength_uses_met():
    kcal = activity_kcal_model("strength_training", 3600, None, 90)
    assert kcal == 4.0 * 90


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
