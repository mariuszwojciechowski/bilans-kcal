from app.services.balance import day_balance, deficit_warning, projected_weekly_change_kg


def test_complete_day_uses_garmin():
    b = day_balance(kcal_in=2000, garmin_total=2600, model_tdee=2400, day_complete=True)
    assert b.kcal_out == 2600
    assert b.out_source == "garmin"
    assert b.estimated is False
    assert b.balance == -600


def test_no_garmin_falls_back_to_model():
    b = day_balance(kcal_in=2000, garmin_total=None, model_tdee=2400, day_complete=False)
    assert b.kcal_out == 2400
    assert b.out_source == "model"
    assert b.estimated is True


def test_day_in_progress_uses_measurement():
    """Dzień w toku bierze pomiar Garmina, bez `max` z modelem teoretycznym
    (decyzja właściciela 2026-09-05 — model potrafił zawyżać wydatek o >1000
    kcal, patrz TODO.md „Poprawa wyliczania kcal na dzień w toku")."""
    b = day_balance(kcal_in=1500, garmin_total=1200, model_tdee=2400, day_complete=False)
    assert b.kcal_out == 1200
    assert b.out_source == "mixed"
    assert b.estimated is True


def test_day_in_progress_without_garmin_falls_back_to_model():
    b = day_balance(kcal_in=1500, garmin_total=None, model_tdee=2400, day_complete=False)
    assert b.kcal_out == 2400
    assert b.out_source == "model"
    assert b.estimated is True


def test_weekly_projection():
    assert projected_weekly_change_kg(-550) == -550 * 7 / 7700


def test_deficit_warning_threshold():
    assert deficit_warning(500, 2600) is None            # 500 < 25% * 2600 = 650
    assert deficit_warning(700, 2600) is not None
