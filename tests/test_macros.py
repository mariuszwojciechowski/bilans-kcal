from app.services.macros import coverage, resolve_norms, who_targets


def test_who_targets_protein_from_weight_default_lifestyle():
    t = who_targets(2000, weight_kg=90)  # domyślnie: rekreacyjnie trenujący
    assert round(t.protein_who_min_g, 1) == 74.7      # WHO 0.83 g/kg
    assert round(t.protein.min_g) == 108               # 1.2 g/kg
    assert round(t.protein.max_g) == 144               # 1.6 g/kg


def test_lifestyle_changes_protein_and_carbs():
    sed = who_targets(2000, weight_kg=80, lifestyle="sedentary")
    end = who_targets(2000, weight_kg=80, lifestyle="endurance")
    st = who_targets(2000, weight_kg=80, lifestyle="strength")
    assert (round(sed.protein.min_g), round(sed.protein.max_g)) == (64, 80)    # 0.8-1.0
    assert (round(end.protein.min_g), round(end.protein.max_g)) == (96, 144)   # 1.2-1.8
    assert (round(st.protein.min_g), round(st.protein.max_g)) == (128, 160)    # 1.6-2.0
    # trenujący: węgle w g/kg; mało aktywny: %E
    assert (end.carbs.min_g, end.carbs.max_g) == (400, 640)   # 5-8 g/kg * 80
    assert sed.carbs.min_g == 0.55 * 2000 / 4
    # tłuszcze trenujących 20-35%E
    assert round(end.fat.min_g, 1) == round(0.20 * 2000 / 9, 1)


def test_senior_floor_applies_over_sedentary_lifestyle():
    t = who_targets(2000, weight_kg=80, age=70, lifestyle="sedentary")
    assert round(t.protein.min_g) == 80    # floor 1.0 g/kg
    assert round(t.protein.max_g) == 96    # floor 1.2 g/kg


def test_pregnant_lifestyle_range():
    t = who_targets(2000, weight_kg=70, sex="F", lifestyle="pregnant")
    assert (round(t.protein.min_g), round(t.protein.max_g)) == (84, 98)  # 1.2-1.4


def test_norms_group_by_age():
    assert resolve_norms("M", 45)["group_id"] == "adult"
    assert resolve_norms("F", 64)["group_id"] == "adult"
    assert resolve_norms("M", 65)["group_id"] == "senior"


def test_senior_group_detected():
    senior = who_targets(2000, weight_kg=80, sex="M", age=70)
    assert senior.group_id == "senior"


def test_sex_override_mechanism(monkeypatch):
    import app.services.macros as m
    norms = {
        "groups": [{"id": "adult", "match": {"age_min": 18}, "protein_g_per_kg_min": 0.83,
                    "protein_cut_g_per_kg": [1.2, 1.6], "fat_energy": [0.15, 0.30],
                    "carbs_energy": [0.55, 0.75], "free_sugars_energy_max": 0.10,
                    "fiber_g_min": 25.0}],
        "sex_overrides": {"M": {"fiber_g_min": 38.0}, "F": {}},
        "lifestyles": {"active": {"label": "x", "protein_g_per_kg": [1.2, 1.6]}},
    }
    monkeypatch.setattr(m, "_norms", lambda: norms)
    assert m.resolve_norms("M", 40)["fiber_g_min"] == 38.0
    assert m.resolve_norms("F", 40)["fiber_g_min"] == 25.0


def test_who_targets_energy_ranges_who_baseline():
    t = who_targets(2000, weight_kg=90, lifestyle="sedentary")  # czyste zakresy WHO %E
    assert round(t.fat.min_g, 1) == 33.3     # 15% * 2000 / 9
    assert round(t.fat.max_g, 1) == 66.7     # 30% * 2000 / 9
    assert t.carbs.min_g == 275.0            # 55% * 2000 / 4
    assert t.carbs.max_g == 375.0            # 75% * 2000 / 4
    assert t.sugars_max_g == 50.0            # 10% * 2000 / 4
    assert t.fiber_min_g == 25.0


def test_coverage_statuses():
    t = who_targets(2000, weight_kg=90, lifestyle="sedentary")
    cov = coverage(t, protein_g=100, fat_g=80, carbs_g=300, fiber_g=10, sugars_g=60)
    assert cov["protein"]["status"] == "above"   # > 90 (0.8-1.0 g/kg * 90)
    assert cov["fat"]["status"] == "above"       # > 66.7
    assert cov["carbs"]["status"] == "ok"
    assert cov["fiber"]["status"] == "below"
    assert cov["sugars"]["status"] == "above"
