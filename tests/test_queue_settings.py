import io
from datetime import date, datetime, time, timedelta

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Activity, PendingMeal, User, WeightLog
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


def test_delete_pending_removes_row_and_photo(db):
    keep = meal_queue.enqueue(db, 1, date.today(), time(9, 0), description="zostaje")
    drop = meal_queue.enqueue(db, 1, date.today(), time(10, 0), photo_bytes=_jpeg())
    drop_photo = meal_queue.PHOTOS_DIR / drop.photo_path

    meal_queue.delete_pending(db, drop)

    assert not drop_photo.exists()
    assert [r.id for r in db.scalars(select(PendingMeal)).all()] == [keep.id]


def test_downscale_accepts_heic():
    """HEIC z iPhone → downscale zwraca poprawny JPEG."""
    import pillow_heif
    pillow_heif.register_heif_opener()
    img = Image.new("RGB", (2000, 1500), (80, 120, 200))
    heif_img = pillow_heif.from_pillow(img)
    buf = io.BytesIO()
    heif_img.save(buf)
    heic_bytes = buf.getvalue()
    result = meal_queue.downscale_photo(heic_bytes)
    out = Image.open(io.BytesIO(result))
    assert out.format == "JPEG"
    assert max(out.size) <= meal_queue.MAX_EDGE_PX


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


# ── TESTY AKTYWNOŚCI ──

def test_manual_activity_kcal_running_with_distance():
    """Bieg z dystansem: kcal = masa × km (ignoruje intensywność)."""
    from app.services.energy import manual_activity_kcal
    kcal, exp = manual_activity_kcal("running", "lekka", 3600, 5000, 70)
    assert kcal == 350  # 70 * 5
    assert "bieg" in exp.lower()


def test_manual_activity_kcal_running_without_distance():
    """Bieg bez dystansu: MET 8/10/12 × masa × czas."""
    from app.services.energy import manual_activity_kcal
    kcal, exp = manual_activity_kcal("running", "umiarkowana", 3600, None, 70)
    assert kcal == 700  # MET 10 * 70 * 1h


def test_manual_activity_kcal_cycling_ignores_distance():
    """Rower liczy z MET, dystans ignorowany."""
    from app.services.energy import manual_activity_kcal
    kcal, exp = manual_activity_kcal("cycling", "intensywna", 3600, 999, 70)
    assert kcal == 700  # MET 10 * 70 * 1h


def test_manual_activity_kcal_strength_training():
    """Siłownia liczy z MET (maxy 3.5 < obwodowo 6.0)."""
    from app.services.energy import manual_activity_kcal
    kcal_maxy, _ = manual_activity_kcal("strength_training", "lekka", 3600, None, 70)
    kcal_obwodo, _ = manual_activity_kcal("strength_training", "intensywna", 3600, None, 70)
    assert kcal_maxy == 245  # MET 3.5 * 70 * 1h
    assert kcal_obwodo == 420  # MET 6.0 * 70 * 1h
    assert kcal_maxy < kcal_obwodo


def test_manual_activity_kcal_walking():
    """Marsz z dystansem: 0.53 × masa × km; bez: MET."""
    from app.services.energy import manual_activity_kcal
    kcal_dist, exp = manual_activity_kcal("walking", "umiarkowana", 3600, 10000, 70)
    assert kcal_dist == 371  # 0.53 * 70 * 10 km
    assert "marsz" in exp.lower()

    kcal_no_dist, _ = manual_activity_kcal("walking", "umiarkowana", 3600, None, 70)
    assert kcal_no_dist == 301  # MET 4.3 * 70 * 1h


def test_default_steps_constant():
    """DEFAULT_STEPS = 5000."""
    from app.services.energy import DEFAULT_STEPS
    assert DEFAULT_STEPS == 5000


