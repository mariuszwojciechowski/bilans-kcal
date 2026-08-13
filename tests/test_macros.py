from app.services.macros import coverage, who_targets


def test_who_targets_protein_from_weight():
    t = who_targets(2000, weight_kg=90)
    assert round(t.protein.min_g, 1) == 74.7          # 0.83 g/kg
    assert round(t.protein_cut.min_g) == 108           # 1.2 g/kg
    assert round(t.protein_cut.max_g) == 144           # 1.6 g/kg


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
