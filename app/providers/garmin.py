"""GarminProvider — nieoficjalna biblioteka `garminconnect` (decyzja D4).

Multi-user: tokeny sesji trzymamy w podkatalogu per użytkownik
(GARMIN_TOKENS_DIR/<user_id>/), stan dwustopniowego logowania (MFA) też
per użytkownik — dwaj testerzy łączą swoje konta Garmina niezależnie."""

from datetime import date, datetime

from garminconnect import Garmin

from ..config import garmin_tokens_dir
from . import ActivityData, DailySummaryData, WeightData


class GarminNotLoggedIn(RuntimeError):
    pass


# stan dwustopniowego logowania z ustawień, keyowany user_id
# (jeśli ktoś zacznie MFA i nie dokończy, wpis zostaje w pamięci — akceptowalne
# przy pilocie <10 osób, nie warto sprzątać ręcznie)
_mfa_state: dict[int, dict] = {}


def tokens_present(user_id: int) -> bool:
    d = garmin_tokens_dir(user_id)
    return d.exists() and any(d.iterdir())


def interactive_login_start(email: str, password: str, user_id: int) -> str:
    """Logowanie z formularza ustawień. Zwraca 'ok' albo 'mfa' (czekamy na kod).
    Hasło nie jest nigdzie zapisywane — idzie wyłącznie do biblioteki Garmina."""
    api = Garmin(email=email, password=password, return_on_mfa=True)
    status, state = api.login()
    if status == "needs_mfa":
        _mfa_state[user_id] = {"api": api, "state": state}
        return "mfa"
    tokens = garmin_tokens_dir(user_id)
    tokens.mkdir(parents=True, exist_ok=True)
    api.client.dump(str(tokens))
    return "ok"


def interactive_login_mfa(code: str, user_id: int) -> str:
    pending = _mfa_state.get(user_id)
    if pending is None:
        raise GarminNotLoggedIn("Brak rozpoczętego logowania — podaj najpierw e-mail i hasło.")
    api = pending["api"]
    api.resume_login(pending["state"], code)
    tokens = garmin_tokens_dir(user_id)
    tokens.mkdir(parents=True, exist_ok=True)
    api.client.dump(str(tokens))
    del _mfa_state[user_id]
    return "ok"


class GarminProvider:
    def __init__(self, user_id: int) -> None:
        self._user_id = user_id
        self._api: Garmin | None = None

    def _client(self) -> Garmin:
        if self._api is None:
            api = Garmin()
            try:
                api.login(str(garmin_tokens_dir(self._user_id)))
            except Exception as exc:  # brak/wygasłe tokeny
                raise GarminNotLoggedIn(
                    "Brak ważnej sesji Garmina. Połącz konto w /settings."
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
