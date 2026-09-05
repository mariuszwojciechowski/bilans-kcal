import os
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH, ensure_dirs


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None

# Czekanie na zwolnienie blokady zapisu, zanim SQLite zwróci "database is locked".
# Zadania w tle (`maybe_sync`, `process_queue` — BackgroundTasks) otwierają własne
# sesje i piszą równolegle z obsługą requestu, więc kolizje zapisów się zdarzają.
BUSY_TIMEOUT_MS = 10_000


def _sqlite_pragmas(dbapi_connection, _record) -> None:
    """PRAGMA ustawiane przy każdym nowym połączeniu.

    - `journal_mode=WAL`: czytający nie blokują piszącego i odwrotnie. Bez tego
      każdy zapis w tle wstrzymywał odczyty (dashboard, `/api/day`). Ustawienie
      jest trwałe w pliku bazy, ale ustawiamy je przy każdym połączeniu — jest
      idempotentne i obejmuje też bazy tworzone od zera (testy).
    - `busy_timeout`: patrz `BUSY_TIMEOUT_MS`; to ustawienie jest per
      połączenie, więc MUSI być tutaj, nie jednorazowo przy starcie.

    Świadomie NIE włączamy `foreign_keys=ON`: to zmiana zachowania, nie
    wydajności — SQLite domyślnie kluczy obcych nie pilnuje, a część kodu
    i testów operuje na `user_id` bez istniejącego wiersza `user`. Do zrobienia
    osobno, razem z przeglądem fixture'ów.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        ensure_dirs()
        _engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
        event.listen(_engine, "connect", _sqlite_pragmas)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    from . import models  # noqa: F401 — rejestracja tabel

    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate(engine)
    # Higiena plików (plan „Szyfrowanie sekretów") — plik bazy tylko dla
    # właściciela procesu. Dopiero tu plik na pewno istnieje (SQLite tworzy go
    # leniwie, przy pierwszym połączeniu — create_all wyżej je wymusza).
    if os.name == "posix" and DB_PATH.exists():
        DB_PATH.chmod(0o600)
        # WAL tworzy obok bazy pliki -wal i -shm z tą samą treścią transakcji —
        # muszą mieć te same prawa co baza, inaczej higiena plików jest pozorna.
        for suffix in ("-wal", "-shm"):
            sidecar = DB_PATH.with_name(DB_PATH.name + suffix)
            if sidecar.exists():
                sidecar.chmod(0o600)


def _migrate(engine) -> None:
    """Proste migracje addytywne (create_all nie dodaje kolumn do istniejących tabel)."""
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(user_profile)"))]
        if cols and "target_weight_kg" not in cols:
            conn.execute(text("ALTER TABLE user_profile ADD COLUMN target_weight_kg FLOAT"))
            conn.commit()
        if cols and "lifestyle" not in cols:
            conn.execute(text(
                "ALTER TABLE user_profile ADD COLUMN lifestyle VARCHAR DEFAULT 'active' NOT NULL"
            ))
            conn.commit()
        if cols and "birth_year" not in cols:
            conn.execute(text("ALTER TABLE user_profile ADD COLUMN birth_year INTEGER"))
            conn.commit()
            conn.execute(text(
                "UPDATE user_profile SET birth_year = CAST(strftime('%Y', birth_date) AS INTEGER) "
                "WHERE birth_year IS NULL"
            ))
            conn.commit()

        user_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(user)"))]
        if user_cols and "password_hash" not in user_cols:
            conn.execute(text("ALTER TABLE user ADD COLUMN password_hash VARCHAR"))
            conn.commit()

        meal_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(meal)"))]
        if meal_cols and "external_id" not in meal_cols:
            conn.execute(text("ALTER TABLE meal ADD COLUMN external_id VARCHAR"))
            conn.commit()
            for (meal_id,) in conn.execute(text("SELECT id FROM meal WHERE external_id IS NULL")):
                conn.execute(text("UPDATE meal SET external_id = :eid WHERE id = :id"),
                             {"eid": uuid.uuid4().hex, "id": meal_id})
            conn.commit()
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_meal_external_id ON meal(external_id)"
            ))
            conn.commit()

        activity_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(activity)"))]
        if activity_cols and "source" not in activity_cols:
            conn.execute(text("ALTER TABLE activity ADD COLUMN source VARCHAR DEFAULT 'garmin'"))
            conn.commit()
        if activity_cols and "kcal_bmr_garmin" not in activity_cols:
            conn.execute(text("ALTER TABLE activity ADD COLUMN kcal_bmr_garmin INTEGER"))
            conn.commit()
        if activity_cols and "steps" not in activity_cols:
            conn.execute(text("ALTER TABLE activity ADD COLUMN steps INTEGER"))
            conn.commit()

        summary_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(daily_summary)"))]
        if summary_cols and "model_total_kcal" not in summary_cols:
            conn.execute(text("ALTER TABLE daily_summary ADD COLUMN model_total_kcal INTEGER"))
            conn.commit()
        if summary_cols and "model_checked_on" not in summary_cols:
            conn.execute(text("ALTER TABLE daily_summary ADD COLUMN model_checked_on DATE"))
            conn.commit()


def get_session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def db_session():
    """Zależność FastAPI: sesja bazy na czas requestu."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()
