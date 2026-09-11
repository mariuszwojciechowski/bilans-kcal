"""StravaProvider — OAuth API Stravy v3.

Działanie:
- get_daily_summary(day) zwraca None dla każdego pola (Strava nie ma dziennego podsumowania).
- get_activities(start, end) pobiera listę aktywności z OAuth token.
- get_weights(start, end) zwraca [] (Strava nie jest źródłem wagi w tym planie).
"""

import json
from datetime import date, datetime, timedelta, timezone
from typing import cast

import httpx
from sqlalchemy.orm import Session

from ..config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI
from ..services import settings as settings_service
from . import ActivityData, DailySummaryData, WeightData

STRAVA_TOKENS_KEY = "strava_tokens"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Ile aktywności w jednym syncu wolno dociągnąć szczegółami (po kcal).
# Limity Stravy: 100 requestów / 15 min, 1000 / dobę, a `maybe_sync` leci
# najwyżej raz na 10 min — 40 zostawia zapas na paginację i odświeżanie tokenu.
DETAIL_FETCH_LIMIT = 40

# Mapowanie sport_type Stravy na typy aktywności aplikacji (jak w energy.py)
STRAVA_SPORT_TYPE_MAP = {
    "Run": "running",
    "Walk": "walking",
    "Ride": "cycling",
    "MountainBikeRide": "cycling",
    "GravelRide": "cycling",
    "RollerSki": "skiing",
    "WeightTraining": "strength_training",
    "Swim": "swimming",
    "CrossFit": "strength_training",
    "Yoga": "yoga",
    "Pilates": "pilates",
    "StairStepper": "other",
    "VirtualRide": "cycling",
    "AlpineSki": "skiing",
    "BackcountrySki": "skiing",
    "NordicSki": "skiing",
}


class StravaProvider:
    def __init__(self, user_id: int, db: Session) -> None:
        self._user_id = user_id
        self._db = db
        self._access_token: str | None = None

    def _get_token(self) -> str:
        """Pobiera access token, odświeżając jeśli wygasł."""
        blob_str = settings_service.get_setting(self._db, self._user_id, STRAVA_TOKENS_KEY)
        if not blob_str:
            raise RuntimeError("Brak podłączonego konta Stravy. Połącz w /settings.")

        blob = json.loads(blob_str)
        access_token = blob.get("access_token")
        expires_at = blob.get("expires_at")
        refresh_token = blob.get("refresh_token")

        if not access_token:
            raise RuntimeError("Brak access token")

        # Jeśli token wygasł lub wygasa w < 5 min, odśwież
        import time
        if expires_at and time.time() >= (expires_at - 300):
            if not refresh_token:
                raise RuntimeError("Brak refresh token")
            try:
                resp = httpx.post(
                    "https://www.strava.com/oauth/token",
                    data={
                        "client_id": STRAVA_CLIENT_ID,
                        "client_secret": STRAVA_CLIENT_SECRET,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                new_blob = resp.json()
                new_blob_str = json.dumps({
                    "access_token": new_blob["access_token"],
                    "refresh_token": new_blob.get("refresh_token", refresh_token),
                    "expires_at": new_blob.get("expires_at"),
                    "scope": new_blob.get("scope", blob.get("scope")),
                })
                settings_service.set_setting(self._db, self._user_id, STRAVA_TOKENS_KEY, new_blob_str)
                access_token = new_blob["access_token"]
            except Exception:
                # Błąd odświeżenia — token jest stracony, kasujemy i rzucamy
                settings_service.set_setting(self._db, self._user_id, STRAVA_TOKENS_KEY, None)
                raise

        return access_token

    def get_daily_summary(self, day: date) -> DailySummaryData:
        """Strava nie ma dziennego podsumowania — zwracamy pusty object."""
        return DailySummaryData(
            date=day,
            kcal_total=None,
            kcal_active=None,
            kcal_bmr=None,
            steps=None,
        )

    def get_weights(self, start: date, end: date) -> list[WeightData]:
        """Strava nie jest źródłem wagi."""
        return []

    def _detail_calories(self, activity_id: int, headers: dict[str, str]) -> int | None:
        """`calories` z DetailedActivity (`/activities/{id}`). Błąd pojedynczej
        aktywności nie może wywrócić całego syncu — wtedy None."""
        try:
            resp = httpx.get(
                f"{STRAVA_API_BASE}/activities/{activity_id}",
                headers=headers,
                params={"include_all_efforts": "false"},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            return None
        value = resp.json().get("calories")
        return round(value) if value else None

    def get_activities(self, start: date, end: date) -> list[ActivityData]:
        """Pobiera aktywności z Stravy za dany zakres dat."""
        access_token = self._get_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        activities: list[ActivityData] = []

        # Strava filtruje po epochu UTC, a zakres dostajemy w dobach lokalnych
        # użytkownika — bierzemy dobę marginesu z każdej strony, a o dniu
        # aktywności decyduje `start_date_local` niżej.
        after = int((datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
                     - timedelta(days=1)).timestamp())
        before = int((datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
                      + timedelta(days=2)).timestamp())

        # Paginacja — Strava zwraca po 30 na request
        page = 1
        per_page = 30
        raw: list[dict] = []

        while True:
            try:
                resp = httpx.get(
                    f"{STRAVA_API_BASE}/athlete/activities",
                    headers=headers,
                    params={
                        "after": after,
                        "before": before,
                        "per_page": per_page,
                        "page": page,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    settings_service.set_setting(self._db, self._user_id, STRAVA_TOKENS_KEY, None)
                raise

            data = resp.json()
            if not data:
                break
            raw.extend(data)

            if len(data) < per_page:
                break
            page += 1

        details_left = DETAIL_FETCH_LIMIT
        for item in raw:
            # Dzień z czasu lokalnego aktywności — `start_date` jest w UTC,
            # więc wieczorny trening wpadałby użytkownikowi na następny dzień.
            stamp = item.get("start_date_local") or item["start_date"]
            activity_date = date.fromisoformat(stamp[:10])

            # Typ aktywności — mapowanie
            sport_type = item.get("sport_type", "unknown")
            activity_type = STRAVA_SPORT_TYPE_MAP.get(sport_type, "other")

            # `/athlete/activities` zwraca SummaryActivity, które **nie ma**
            # pola `calories` — jest tylko w DetailedActivity. Bez kcal
            # aktywność nie wchodzi do wydatku (`day.py`), więc dociągamy
            # szczegóły per aktywność (limit requestów Stravy — stąd
            # DETAIL_FETCH_LIMIT). Gdy się nie uda, zostaje `kilojoules`
            # (praca mechaniczna, sensowne przybliżenie dla kolarstwa).
            kcal = item.get("calories")
            if kcal is None and details_left > 0:
                details_left -= 1
                kcal = self._detail_calories(item["id"], headers)
            if kcal is None and item.get("kilojoules"):
                kcal = round(item["kilojoules"])
            if not kcal:
                kcal = None  # 0 znaczy brak danych, nie zero spalonych kcal

            avg_hr = item.get("average_heartrate")

            activities.append(ActivityData(
                garmin_id=f"strava-{item['id']}",
                date=activity_date,
                type=activity_type,
                duration_s=int(item.get("elapsed_time", 0)),
                distance_m=item.get("distance"),
                kcal=kcal,
                avg_hr=round(avg_hr) if avg_hr else None,
                kcal_bmr=None,  # Strava nie podaje BMR
                steps=None,  # Strava nie podaje kroków dla większości aktywności
            ))

        return activities


def tokens_present(db: Session, user_id: int) -> bool:
    """Sprawdza, czy user ma podłączone konto Stravy."""
    return settings_service.get_setting(db, user_id, STRAVA_TOKENS_KEY) is not None
