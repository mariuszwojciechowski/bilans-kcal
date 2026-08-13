import io
from datetime import date, datetime, time, timedelta

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PendingMeal, User
from app.services import meal_queue, settings as settings_service


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(meal_queue, "PHOTOS_DIR", tmp_path / "photos")
    user = User(email="t@t")
    session.add(user)
    session.commit()
    yield session
    session.close()


def _jpeg(w=3000, h=2000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 180, 90)).save(buf, format="JPEG")
    return buf.getvalue()


def test_downscale_limits_long_edge():
    out = meal_queue.downscale_photo(_jpeg())
    img = Image.open(io.BytesIO(out))
    assert max(img.size) <= meal_queue.MAX_EDGE_PX
    assert img.format == "JPEG"


def test_enqueue_photo_saves_reduced_file(db):
    row = meal_queue.enqueue(db, 1, date.today(), time(12, 0), photo_bytes=_jpeg())
    path = meal_queue.PHOTOS_DIR / row.photo_path
    assert path.exists()
    assert path.stat().st_size < len(_jpeg())


def test_purge_expired_respects_retention(db):
    fresh = meal_queue.enqueue(db, 1, date.today(), time(9, 0), description="świeży")
    old = meal_queue.enqueue(db, 1, date.today(), time(9, 0), photo_bytes=_jpeg())
    old.created_at = datetime.utcnow() - timedelta(days=meal_queue.RETENTION_DAYS + 1)
    old_photo = meal_queue.PHOTOS_DIR / old.photo_path
    db.commit()

    removed = meal_queue.purge_expired(db)

    assert removed == 1
    assert not old_photo.exists()
    left = db.scalars(select(PendingMeal)).all()
    assert [r.id for r in left] == [fresh.id]


def test_settings_roundtrip_and_env(db, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings_service.set_setting(db, 1, "gemini_api_key", "AQ.test123")
    assert settings_service.get_setting(db, 1, "gemini_api_key") == "AQ.test123"
    settings_service.apply_llm_env(db, 1)
    import os
    assert os.environ["GEMINI_API_KEY"] == "AQ.test123"
    assert settings_service.masked("AQ.test123").endswith("t123")
    settings_service.set_setting(db, 1, "gemini_api_key", None)
    assert settings_service.get_setting(db, 1, "gemini_api_key") is None
