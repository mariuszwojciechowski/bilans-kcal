"""Warstwa dostępu do danych zdrowotnych — wymienna implementacja (decyzja D4/D7):
MVP używa nieoficjalnego API Garmin Connect; docelowo na mobile Health Connect /
HealthKit dostarczą te same struktury."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class DailySummaryData:
    date: date
    kcal_total: int | None
    kcal_active: int | None
    kcal_bmr: int | None
    steps: int | None


@dataclass
class WeightData:
    date: date
    weight_kg: float


@dataclass
class ActivityData:
    garmin_id: str
    date: date
    type: str
    duration_s: int
    distance_m: float | None
    kcal: int | None
    avg_hr: int | None
    kcal_bmr: int | None = None  # spoczynek zegarka za czas trwania (Garmin: bmrCalories)
    steps: int | None = None  # kroki zarejestrowane przez zegarek dla tej aktywności


class DataProvider(Protocol):
    def get_daily_summary(self, day: date) -> DailySummaryData: ...

    def get_weights(self, start: date, end: date) -> list[WeightData]: ...

    def get_activities(self, start: date, end: date) -> list[ActivityData]: ...


def get_provider_for_user(db, user_id) -> "DataProvider | None":
    """Wybór providera dla usera (priorytet: Garmin > Strava > None).
    Garmin ma priorytet, aby uniknąć duplikatów (Garmin zwykle eksportuje do Stravy)."""
    from . import garmin as garmin_provider
    from . import strava as strava_provider

    if garmin_provider.tokens_present(db, user_id):
        return garmin_provider.GarminProvider(user_id, db)
    if strava_provider.tokens_present(db, user_id):
        return strava_provider.StravaProvider(user_id, db)
    return None
