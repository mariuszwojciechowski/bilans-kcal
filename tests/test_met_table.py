"""Tabela MET jako dane, nie kod — WYMAGANIA.md §4 (TODO.md „Tabela MET jako
dane…"). Wzorzec `test_macros.py`/`who_norms.json`: plik jest jedynym źródłem
prawdy, brak/inna zawartość pliku realnie zmienia wynik."""
import json

import pytest

from app.services import energy


def test_met_table_loads_and_has_sources():
    data = energy._met()
    assert data["meta"]["sources"]


def test_manual_has_three_intensities_per_type():
    data = energy._met()
    for activity_type, mets in data["manual"]["types"].items():
        assert len(mets) == 3, activity_type


def test_cycling_thresholds_increasing_and_last_is_null():
    data = energy._met()
    thresholds = data["cycling"]["met_by_speed_kmh"]
    limits = [row[0] for row in thresholds]
    assert limits[-1] is None
    finite = [limit for limit in limits if limit is not None]
    assert finite == sorted(finite)


def test_default_met_from_file_changes_activity_kcal_model(tmp_path, monkeypatch):
    """Dowód, że `activity_kcal_model` naprawdę czyta z pliku, nie z kodu:
    podmieniamy `MET_PATH` na plik z innym `default_met` i czyścimy cache —
    nieznany typ aktywności ma policzyć się z nową wartością."""
    original = json.loads(energy.MET_PATH.read_text())
    modified = json.loads(json.dumps(original))
    modified["garmin_activities"]["default_met"] = 9.0
    alt_path = tmp_path / "met_table.json"
    alt_path.write_text(json.dumps(modified))

    monkeypatch.setattr(energy, "MET_PATH", alt_path)
    energy._met.cache_clear()
    try:
        # netto (MET-1) * weight * hours; typ nieznany -> default_met
        kcal = energy.activity_kcal_model("some_unknown_type", 3600, None, 70)
        assert kcal == pytest.approx((9.0 - 1) * 70 * 1.0)
    finally:
        energy._met.cache_clear()  # przywróć realny plik dla kolejnych testów


def test_default_steps_matches_file():
    assert energy.DEFAULT_STEPS == energy._met()["steps"]["default_steps"]
