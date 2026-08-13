"""Moduł M5: dzienny bilans energetyczny.

bilans = kcal spożyte − kcal spalone. Wydatek: pomiar Garmina (źródło prawdy);
gdy dzień niedomknięty lub brak danych z zegarka — model teoretyczny (oznaczone)."""

from dataclasses import dataclass

KCAL_PER_KG_FAT = 7700


@dataclass
class DayBalance:
    kcal_in: float
    kcal_out: float
    out_source: str  # "garmin" | "model" | "mixed"
    estimated: bool

    @property
    def balance(self) -> float:
        return self.kcal_in - self.kcal_out


def day_balance(
    kcal_in: float,
    garmin_total: float | None,
    model_tdee: float,
    day_complete: bool,
) -> DayBalance:
    if garmin_total is None:
        return DayBalance(kcal_in, model_tdee, "model", True)
    if day_complete:
        return DayBalance(kcal_in, garmin_total, "garmin", False)
    # Dzień w toku: częściowy pomiar Garmina albo prognoza z modelu — bierzemy większe,
    # żeby nie zaniżać wydatku przed końcem dnia (Garmin dosyła dane co kilka godzin).
    return DayBalance(kcal_in, max(garmin_total, model_tdee), "mixed", True)


def projected_weekly_change_kg(avg_daily_balance: float) -> float:
    return avg_daily_balance * 7 / KCAL_PER_KG_FAT


def deficit_warning(target_deficit: int, tdee: float) -> str | None:
    """Deficyt > ~25% TDEE jest zdrowotnie i behawioralnie niezrównoważony."""
    if tdee > 0 and target_deficit > 0.25 * tdee:
        return (
            f"Cel deficytu {target_deficit} kcal przekracza 25% dziennego wydatku "
            f"({tdee:.0f} kcal) — rozważ łagodniejsze tempo."
        )
    return None
