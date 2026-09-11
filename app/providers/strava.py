"""StravaProvider — OAuth API Stravy v3.

Działanie:
- get_daily_summary(day) zwraca None dla każdego pola (Strava nie ma dziennego podsumowania).
- get_activities(start, end) pobiera listę aktywności z OAuth token.
- get_weights(start, end) zwraca [] (Strava nie jest źródłem wagi w tym planie).
"""

import json
from datetime import date
from typing import cast

import httpx
from sqlalchemy.orm import Session

from ..config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI
from ..services import settings as settings_service
from . import ActivityData, DailySummaryData, WeightData

STRAVA_TOKENS_KEY = "strava_tokens"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

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

    def get_activities(self, start: date, end: date) -> list[ActivityData]:
        """Pobiera aktywności z Stravy za dany zakres dat."""
        access_token = self._get_token()
        activities: list[ActivityData] = []

        # Paginacja — Strava zwraca po 30 na request
        page = 1
        per_page = 30
        after = int(start.timestamp()) if start else None
        before = int((end.replace(day=31) if end.month == 12 else end.replace(month=end.month + 1, day=1)).timestamp())

        while True:
            try:
                resp = httpx.get(
                    f"{STRAVA_API_BASE}/athlete/activities",
                    headers={"Authorization": f"Bearer {access_token}"},
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

            for item in data:
                activity_date = date.fromisoformat(item["start_date"][:10])

                # Typ aktywności — mapowanie
                sport_type = item.get("sport_type", "unknown")
                activity_type = STRAVA_SPORT_TYPE_MAP.get(sport_type, "other")

                # Kalorie (zwraca int albo None; może być 0 dla niektórych aktywności)
                kcal = item.get("calories")
                if kcal == 0:
                    kcal = None  # Zero znaczy brak danych

                activities.append(ActivityData(
                    garmin_id=f"strava-{item['id']}",
                    date=activity_date,
                    type=activity_type,
                    duration_s=int(item.get("elapsed_time", 0)),
                    distance_m=item.get("distance"),
                    kcal=kcal,
                    avg_hr=item.get("average_heartrate"),
                    kcal_bmr=None,  # Strava nie podaje BMR
                    steps=None,  # Strava nie podaje kroków dla większości aktywności
                ))

            if len(data) < per_page:
                break
            page += 1

        return activities


def tokens_present(db: Session, user_id: int) -> bool:
    """Sprawdza, czy user ma podłączone konto Stravy."""
    return settings_service.get_setting(db, user_id, STRAVA_TOKENS_KEY) is not None
