"""GarminProvider — nieoficjalna biblioteka `garminconnect` (decyzja D4).

Multi-user: tokeny sesji trzymamy zaszyfrowane w bazie (AppSetting, klucz
GARMIN_TOKENS_KEY) — nie jako jawne pliki na dysku (plan „Szyfrowanie sekretów
użytkownika", część B). Przy każdym użyciu materializują się do prywatnego
katalogu tymczasowego (PrivateTmp=true w systemd), kasowanego natychmiast po
zalogowaniu. Stan dwustopniowego logowania (MFA) też per użytkownik — dwaj
testerzy łączą swoje konta Garmina niezależnie."""

import base64
import json
import shutil
import stat
import tempfile
from datetime import date, datetime
from pathlib import Path

from garminconnect import Garmin
from sqlalchemy.orm import Session

from ..config import GARMIN_TOKENS_DIR
from ..services import settings as settings_service
from . import ActivityData, DailySummaryData, WeightData

GARMIN_TOKENS_KEY = "garmin_tokens"


class GarminNotLoggedIn(RuntimeError):
    pass


# stan dwustopniowego logowania z ustawień, keyowany user_id
# (jeśli ktoś zacznie MFA i nie dokończy, wpis zostaje w pamięci — akceptowalne
# przy pilocie <10 osób, nie warto sprzątać ręcznie)
_mfa_state: dict[int, dict] = {}


def _dir_to_blob(dirpath: Path) -> str:
    """Pakuje pliki katalogu tokenów do jednego JSON-a (base64, bezpieczne dla
    binariów) — to jest wartość, którą settings_service szyfruje i zapisuje."""
    files = {}
    for f in dirpath.iterdir():
        if f.is_file():
            files[f.name] = base64.b64encode(f.read_bytes()).decode()
    return json.dumps(files)


def _blob_to_dir(blob: str, dirpath: Path) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    os_chmod_700(dirpath)
    for name, b64 in json.loads(blob).items():
        (dirpath / name).write_bytes(base64.b64decode(b64))


def os_chmod_700(dirpath: Path) -> None:
    dirpath.chmod(stat.S_IRWXU)  # rwx------


def _dump_tokens(db: Session, user_id: int, api: Garmin) -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="fk-garmin-"))
    try:
        os_chmod_700(tmpdir)
        api.client.dump(str(tmpdir))
        blob = _dir_to_blob(tmpdir)
        settings_service.set_setting(db, user_id, GARMIN_TOKENS_KEY, blob)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def tokens_present(db: Session, user_id: int) -> bool:
    return settings_service.get_setting(db, user_id, GARMIN_TOKENS_KEY) is not None


def interactive_login_start(db: Session, email: str, password: str, user_id: int) -> str:
    """Logowanie z formularza ustawień. Zwraca 'ok' albo 'mfa' (czekamy na kod).
    Hasło nie jest nigdzie zapisywane — idzie wyłącznie do biblioteki Garmina."""
    api = Garmin(email=email, password=password, return_on_mfa=True)
    status, state = api.login()
    if status == "needs_mfa":
        _mfa_state[user_id] = {"api": api, "state": state}
        return "mfa"
    _dump_tokens(db, user_id, api)
    return "ok"


def interactive_login_mfa(db: Session, code: str, user_id: int) -> str:
    pending = _mfa_state.get(user_id)
    if pending is None:
        raise GarminNotLoggedIn("Brak rozpoczętego logowania — podaj najpierw e-mail i hasło.")
    api = pending["api"]
    api.resume_login(pending["state"], code)
    _dump_tokens(db, user_id, api)
    del _mfa_state[user_id]
    return "ok"


def migrate_tokens_dirs_to_db(db: Session) -> int:
    """Migracja jednorazowa: istniejące katalogi tokenów na dysku
    (GARMIN_TOKENS_DIR/<user_id>/) wciąga do bazy jako zaszyfrowany blob i
    kasuje katalog. Wołana przy starcie procesu — idempotentna (katalog, który
    już zmigrował, nie istnieje, więc drugie wywołanie nic nie robi)."""
    if not GARMIN_TOKENS_DIR.exists():
        return 0
    migrated = 0
    for entry in GARMIN_TOKENS_DIR.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        if not any(entry.iterdir()):
            continue
        user_id = int(entry.name)
        settings_service.set_setting(db, user_id, GARMIN_TOKENS_KEY, _dir_to_blob(entry))
        shutil.rmtree(entry, ignore_errors=True)
        migrated += 1
    return migrated


class GarminProvider:
    def __init__(self, user_id: int, db: Session) -> None:
        self._user_id = user_id
        self._db = db
        self._api: Garmin | None = None

    def _client(self) -> Garmin:
        if self._api is None:
            blob = settings_service.get_setting(self._db, self._user_id, GARMIN_TOKENS_KEY)
            if blob is None:
                raise GarminNotLoggedIn("Brak ważnej sesji Garmina. Połącz konto w /settings.")
            tmpdir = Path(tempfile.mkdtemp(prefix="fk-garmin-"))
            try:
                _blob_to_dir(blob, tmpdir)
                api = Garmin()
                try:
                    api.login(str(tmpdir))
                except Exception as exc:  # tokeny wygasłe/uszkodzone
                    raise GarminNotLoggedIn(
                        "Brak ważnej sesji Garmina. Połącz konto w /settings."
                    ) from exc
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
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
                    kcal_bmr=int(a["bmrCalories"]) if a.get("bmrCalories") else None,
                    steps=int(a["steps"]) if a.get("steps") else None,
                )
            )
        return out
