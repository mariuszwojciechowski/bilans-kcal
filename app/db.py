import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH, ensure_dirs


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        ensure_dirs()
        _engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    from . import models  # noqa: F401 — rejestracja tabel

    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate(engine)


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
