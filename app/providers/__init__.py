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


class DataProvider(Protocol):
    def get_daily_summary(self, day: date) -> DailySummaryData: ...

    def get_weights(self, start: date, end: date) -> list[WeightData]: ...

    def get_activities(self, start: date, end: date) -> list[ActivityData]: ...
