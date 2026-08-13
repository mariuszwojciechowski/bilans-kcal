from app.services.macros import coverage, resolve_norms, who_targets


def test_who_targets_protein_from_weight():
    t = who_targets(2000, weight_kg=90)
    assert round(t.protein.min_g, 1) == 74.7          # 0.83 g/kg
    assert round(t.protein_cut.min_g) == 108           # 1.2 g/kg
    assert round(t.protein_cut.max_g) == 144           # 1.6 g/kg


def test_norms_group_by_age():
    assert resolve_norms("M", 45)["group_id"] == "adult"
    assert resolve_norms("F", 64)["group_id"] == "adult"
    assert resolve_norms("M", 65)["group_id"] == "senior"


def test_senior_protein_minimum_higher():
    adult = who_targets(2000, weight_kg=80, sex="M", age=45)
    senior = who_targets(2000, weight_kg=80, sex="M", age=70)
    assert round(adult.protein.min_g, 1) == 66.4      # 0.83 g/kg
    assert round(senior.protein.min_g, 1) == 80.0     # 1.0 g/kg (PROT-AGE/ESPEN)
    assert senior.group_id == "senior"


def test_sex_override_mechanism(monkeypatch):
    import app.services.macros as m
    norms = {
        "groups": [{"id": "adult", "match": {"age_min": 18}, "protein_g_per_kg_min": 0.83,
                    "protein_cut_g_per_kg": [1.2, 1.6], "fat_energy": [0.15, 0.30],
                    "carbs_energy": [0.55, 0.75], "free_sugars_energy_max": 0.10,
                    "fiber_g_min": 25.0}],
        "sex_overrides": {"M": {"fiber_g_min": 38.0}, "F": {}},
    }
    monkeypatch.setattr(m, "_norms", lambda: norms)
    assert m.resolve_norms("M", 40)["fiber_g_min"] == 38.0
    assert m.resolve_norms("F", 40)["fiber_g_min"] == 25.0


def test_who_targets_energy_ranges():
    t = who_targets(2000, weight_kg=90)
    assert round(t.fat.min_g, 1) == 33.3     # 15% * 2000 / 9
    assert round(t.fat.max_g, 1) == 66.7     # 30% * 2000 / 9
    assert t.carbs.min_g == 275.0            # 55% * 2000 / 4
    assert t.carbs.max_g == 375.0            # 75% * 2000 / 4
    assert t.sugars_max_g == 50.0            # 10% * 2000 / 4
    assert t.fiber_min_g == 25.0


def test_coverage_statuses():
    t = who_targets(2000, weight_kg=90)
    cov = coverage(t, protein_g=100, fat_g=80, carbs_g=300, fiber_g=10, sugars_g=60)
    assert cov["protein"]["status"] == "ok"      # >= 74.7
    assert cov["fat"]["status"] == "above"       # > 66.7
    assert cov["carbs"]["status"] == "ok"
    assert cov["fiber"]["status"] == "below"
    assert cov["sugars"]["status"] == "above"
