"""GarminProvider — nieoficjalna biblioteka `garminconnect` (decyzja D4).

Logowanie: jednorazowo interaktywnie przez scripts/garmin_login.py (obsługa MFA);
tokeny sesji trafiają do ~/.fit-krasnal/garth (poza repo). Tutaj tylko wznawiamy
sesję z tokenstore — bez haseł w kodzie i konfiguracji aplikacji."""

from datetime import date, datetime

from garminconnect import Garmin

from ..config import GARMIN_TOKENS_DIR
from . import ActivityData, DailySummaryData, WeightData


class GarminNotLoggedIn(RuntimeError):
    pass


# stan dwustopniowego logowania z ustawień (MVP: jeden użytkownik, pamięć procesu)
_mfa_state: dict | None = None


def tokens_present() -> bool:
    return GARMIN_TOKENS_DIR.exists() and any(GARMIN_TOKENS_DIR.iterdir())


def interactive_login_start(email: str, password: str) -> str:
    """Logowanie z formularza ustawień. Zwraca 'ok' albo 'mfa' (czekamy na kod).
    Hasło nie jest nigdzie zapisywane — idzie wyłącznie do biblioteki Garmina."""
    global _mfa_state
    api = Garmin(email=email, password=password, return_on_mfa=True)
    status, state = api.login()
    if status == "needs_mfa":
        _mfa_state = {"api": api, "state": state}
        return "mfa"
    GARMIN_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    api.client.dump(str(GARMIN_TOKENS_DIR))
    return "ok"


def interactive_login_mfa(code: str) -> str:
    global _mfa_state
    if _mfa_state is None:
        raise GarminNotLoggedIn("Brak rozpoczętego logowania — podaj najpierw e-mail i hasło.")
    api = _mfa_state["api"]
    api.resume_login(_mfa_state["state"], code)
    GARMIN_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    api.client.dump(str(GARMIN_TOKENS_DIR))
    _mfa_state = None
    return "ok"


class GarminProvider:
    def __init__(self) -> None:
        self._api: Garmin | None = None

    def _client(self) -> Garmin:
        if self._api is None:
            api = Garmin()
            try:
                api.login(str(GARMIN_TOKENS_DIR))
            except Exception as exc:  # brak/wygasłe tokeny
                raise GarminNotLoggedIn(
                    "Brak ważnej sesji Garmina. Uruchom: python scripts/garmin_login.py"
                ) from exc
            self._api = api
        return self._api

    def get_daily_summary(self, day: date) -> DailySummaryData:
        stats = self._client().get_user_summary(day.isoformat())
        return DailySummaryData(
            date=day,
            kcal_total=stats.get("totalKilocalories"),
            kcal_active=stats.get("activeKilocalories"),
            kcal_bmr=stats.get("bmrKilocalories"),
            steps=stats.get("totalSteps"),
        )

    def get_weights(self, start: date, end: date) -> list[WeightData]:
        data = self._client().get_body_composition(start.isoformat(), end.isoformat())
        out: list[WeightData] = []
        for entry in data.get("dateWeightList", []):
            weight_g = entry.get("weight")
            cal_date = entry.get("calendarDate")
            if weight_g and cal_date:
                out.append(
                    WeightData(
                        date=datetime.strptime(cal_date, "%Y-%m-%d").date(),
                        weight_kg=round(weight_g / 1000.0, 2),
                    )
                )
        return out

    def get_activities(self, start: date, end: date) -> list[ActivityData]:
        activities = self._client().get_activities_by_date(start.isoformat(), end.isoformat())
        out: list[ActivityData] = []
        for a in activities:
            start_local = a.get("startTimeLocal", "")
            try:
                act_date = datetime.strptime(start_local[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            out.append(
                ActivityData(
                    garmin_id=str(a.get("activityId")),
                    date=act_date,
                    type=(a.get("activityType") or {}).get("typeKey", "unknown"),
                    duration_s=int(a.get("duration") or 0),
                    distance_m=a.get("distance"),
                    kcal=int(a["calories"]) if a.get("calories") else None,
                    avg_hr=int(a["averageHR"]) if a.get("averageHR") else None,
                )
            )
        return out
