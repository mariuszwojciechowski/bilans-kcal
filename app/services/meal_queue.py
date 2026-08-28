"""Kolejka posiłków offline (M4b).

Gdy nie ma klucza LLM albo szacowanie się nie powiedzie (np. brak internetu
w roamingu), posiłek trafia do kolejki: opis i/lub zdjęcie w zredukowanej,
wystarczającej dla LLM jakości. Po podaniu klucza w ustawieniach kolejka jest
przetwarzana w tle. Retencja nieprzetworzonych wpisów: 21 dni. Zdjęcia po
przetworzeniu (i wpisy po wygaśnięciu) są kasowane."""

import io
import json
import logging
from datetime import date, datetime, time, timedelta

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PHOTOS_DIR
from ..models import Meal, PendingMeal
from . import meal_vision

logger = logging.getLogger(__name__)

RETENTION_DAYS = 21
MAX_EDGE_PX = 1280
JPEG_QUALITY = 82


def downscale_photo(image_bytes: bytes) -> bytes:
    """Redukcja do rozmiaru wystarczającego dla LLM: max 1280 px dłuższy bok, JPEG."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def enqueue(
    db: Session,
    user_id: int,
    day: date,
    at: time,
    description: str | None = None,
    note: str | None = None,
    photo_bytes: bytes | None = None,
) -> PendingMeal:
    photo_path = None
    if photo_bytes is not None:
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        photo_path = f"pending_{datetime.now():%Y%m%d_%H%M%S_%f}.jpg"
        (PHOTOS_DIR / photo_path).write_bytes(downscale_photo(photo_bytes))
    row = PendingMeal(user_id=user_id, date=day, time=at, description=description,
                      note=note, photo_path=photo_path)
    db.add(row)
    db.commit()
    return row


def _delete_photo(photo_path: str | None) -> None:
    if photo_path:
        (PHOTOS_DIR / photo_path).unlink(missing_ok=True)


def delete_pending(db: Session, pending: PendingMeal) -> None:
    """Usuwa wpis z kolejki wraz ze zdjęciem (rezygnacja z przetwarzania)."""
    _delete_photo(pending.photo_path)
    db.delete(pending)
    db.commit()


def purge_expired(db: Session) -> int:
    """Usuwa nieprzetworzone wpisy starsze niż RETENTION_DAYS (wraz ze zdjęciami)."""
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    expired = db.scalars(select(PendingMeal).where(PendingMeal.created_at < cutoff)).all()
    for row in expired:
        _delete_photo(row.photo_path)
        db.delete(row)
    db.commit()
    return len(expired)


def meal_from_estimate(user_id: int, day: date, at: time | None,
                       estimate: "meal_vision.MealEstimate", source: str) -> Meal:
    return Meal(
        user_id=user_id,
        date=day,
        time=at,
        description=estimate.description,
        photo_path=None,  # przetworzone zdjęcia kasujemy — nie trzymamy ich przy posiłku
        kcal=round(estimate.kcal),
        kcal_min=round(estimate.kcal_min),
        kcal_max=round(estimate.kcal_max),
        protein_g=round(sum(i.protein_g for i in estimate.items), 1),
        fat_g=round(sum(i.fat_g for i in estimate.items), 1),
        carbs_g=round(sum(i.carbs_g for i in estimate.items), 1),
        fiber_g=round(sum(i.fiber_g for i in estimate.items), 1),
        sugars_g=round(sum(i.sugars_g for i in estimate.items), 1),
        items_json=json.dumps([i.model_dump() for i in estimate.items], ensure_ascii=False),
        assumptions_json=json.dumps(estimate.assumptions, ensure_ascii=False),
        source=source,
    )


def process_queue(user_id: int) -> dict:
    """Przetwarza zaległe posiłki (najstarsze najpierw). Otwiera własną sesję DB —
    nadaje się do BackgroundTasks. Przerywa, gdy LLM nieskonfigurowany."""
    from ..db import get_session
    from . import settings as settings_service

    db = get_session()
    processed = failed = 0
    try:
        keys = settings_service.get_llm_keys(db, user_id)
        purge_expired(db)
        pending = db.scalars(
            select(PendingMeal).where(PendingMeal.user_id == user_id)
            .order_by(PendingMeal.created_at)
        ).all()
        for row in pending:
            try:
                if row.photo_path:
                    photo = (PHOTOS_DIR / row.photo_path).read_bytes()
                    estimate = meal_vision.estimate_from_photo(
                        photo, "jpg", row.note,
                        gemini_key=keys.gemini, anthropic_key=keys.anthropic)
                    source = "photo"
                else:
                    estimate = meal_vision.estimate_from_text(
                        row.description or "",
                        gemini_key=keys.gemini, anthropic_key=keys.anthropic)
                    source = "text"
            except meal_vision.MealVisionNotConfigured:
                logger.info("Kolejka: LLM nieskonfigurowany — przerywam.")
                break
            except FileNotFoundError:
                _delete_photo(row.photo_path)
                db.delete(row)
                db.commit()
                continue
            except Exception as exc:
                logger.warning("Kolejka: posiłek %s nieprzetworzony: %s", row.id, exc)
                failed += 1
                continue
            db.add(meal_from_estimate(user_id, row.date, row.time, estimate, source))
            _delete_photo(row.photo_path)
            db.delete(row)
            db.commit()
            processed += 1
        return {"processed": processed, "failed": failed}
    finally:
        db.close()
