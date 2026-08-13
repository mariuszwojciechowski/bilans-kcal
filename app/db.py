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


def get_session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()
