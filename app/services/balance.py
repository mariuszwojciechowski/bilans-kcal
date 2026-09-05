"""Moduł M5: dzienny bilans energetyczny.

bilans = kcal spożyte − kcal spalone. Wydatek: pomiar Garmina (źródło prawdy),
także dla dnia w toku — model teoretyczny zostaje wyłącznie fallbackiem, gdy
zegarek nie dał żadnych danych (decyzja właściciela 2026-09-05, patrz TODO.md
„Poprawa wyliczania kcal na dzień w toku"; wcześniej dzień w toku brał
max(pomiar, model), co przy zawyżonym modelu dawało błąd rzędu 1000+ kcal)."""

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
    manual_kcal: float = 0.0,
) -> DayBalance:
    """manual_kcal: suma kcal ręcznie wpisanych aktywności — Garmin ich nie widział,
    więc u użytkownika z zegarkiem dolicza się do pomiaru osobno."""
    if garmin_total is None:
        return DayBalance(kcal_in, model_tdee, "model", True)
    measured = garmin_total + manual_kcal
    if day_complete:
        return DayBalance(kcal_in, measured, "garmin", False)
    # Dzień w toku: pomiar Garmina, choć częściowy — bez `max` z modelem teoretycznym.
    # Total Garmina w ciągu dnia nie jest zaniżony o BMR (spoczynek jest liczony za
    # całą dobę od rana), brakuje mu tylko przyszłych aktywności — model tylko je
    # zgadywał i potrafił chybić o >1000 kcal (patrz TODO.md). `estimated=True`,
    # bo wydatek jeszcze urośnie, gdy zegarek dośle dane.
    return DayBalance(kcal_in, measured, "mixed", True)


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
