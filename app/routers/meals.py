"""Posiłki: zapis (zdjęcie/tekst/ręcznie), kolejka offline, zapisane szablony."""
import json
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..config import MAX_PHOTO_BYTES
from ..db import db_session
from ..deps import require_llm_consent
from ..models import Meal, PendingMeal, SavedMeal, User, UserProfile
from ..services import meal_queue, meal_vision
from ..services import settings as settings_service
from ..services import usage as usage_service
from ..services.clock import user_time, user_today
from ..services.sync import maybe_sync

router = APIRouter()


def _queue_meal(db: Session, user_id: int, day: date, reason: str,
                description: str | None = None, note: str | None = None,
                photo_bytes: bytes | None = None) -> dict:
    profile = db.get(UserProfile, user_id)
    meal_queue.enqueue(db, user_id, day, user_time(profile), description=description,
                       note=note, photo_bytes=photo_bytes)
    return {
        "queued": True,
        "message": f"Posiłek zapisany do kolejki ({reason}). Zostanie przetworzony "
                   f"automatycznie, gdy LLM będzie dostępny (retencja: 21 dni).",
    }


@router.post("/api/meals/photo", dependencies=[Depends(require_llm_consent)])
async def estimate_meal_photo(
    background: BackgroundTasks,
    photo: UploadFile = File(...),
    note: str | None = Form(None),
    day: date | None = Form(None),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """Krok 1: zdjęcie → szacunek (draft do korekty; nic nie zapisujemy).
    Bez klucza LLM / bez internetu: posiłek trafia do kolejki offline."""
    background.add_task(maybe_sync, user.id)
    usage_service.bump(db, user.id, "meal_photo")
    keys = settings_service.get_llm_keys(db, user.id)
    data = await photo.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Zdjęcie za duże (limit 15 MB)")
    try:
        data = meal_queue.downscale_photo(data)
    except Exception as exc:
        raise HTTPException(422, f"Nie można odczytać zdjęcia: {exc}")
    ext = "jpg"
    target_day = day or user_today(db.get(UserProfile, user.id))
    if not meal_vision.llm_configured(keys.gemini, keys.anthropic):
        return _queue_meal(db, user.id, target_day, "brak klucza LLM",
                           note=note, photo_bytes=data)
    try:
        estimate = meal_vision.estimate_from_photo(data, ext, note,
                                                    gemini_key=keys.gemini,
                                                    anthropic_key=keys.anthropic)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        return _queue_meal(db, user.id, target_day, "szacowanie nie powiodło się",
                           note=note, photo_bytes=data)
    # zdjęcia nie przechowujemy — po przetworzeniu jest niepotrzebne (decyzja: retencja tylko w kolejce)
    return {"photo_path": None, "kcal": round(estimate.kcal), **estimate.model_dump()}


@router.post("/api/meals/text", dependencies=[Depends(require_llm_consent)])
def estimate_meal_text(
    background: BackgroundTasks,
    description: str = Form(...),
    day: date | None = Form(None),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """Krok 1 (wariant tekstowy): opis → szacunek. Fallback: kolejka offline."""
    background.add_task(maybe_sync, user.id)
    usage_service.bump(db, user.id, "meal_text")
    keys = settings_service.get_llm_keys(db, user.id)
    target_day = day or user_today(db.get(UserProfile, user.id))
    if not meal_vision.llm_configured(keys.gemini, keys.anthropic):
        return _queue_meal(db, user.id, target_day, "brak klucza LLM", description=description)
    try:
        estimate = meal_vision.estimate_from_text(description,
                                                   gemini_key=keys.gemini,
                                                   anthropic_key=keys.anthropic)
    except Exception:
        return _queue_meal(db, user.id, target_day, "szacowanie nie powiodło się",
                           description=description)
    return {"photo_path": None, "kcal": round(estimate.kcal), **estimate.model_dump()}


class MealIn(BaseModel):
    date: date
    time: str | None = None
    description: str
    photo_path: str | None = None
    kcal: float
    kcal_min: float | None = None
    kcal_max: float | None = None
    protein_g: float = 0
    fat_g: float = 0
    carbs_g: float = 0
    fiber_g: float = 0
    sugars_g: float = 0
    items: list | None = None
    assumptions: list | None = None
    source: str = "photo"


@router.post("/api/meals")
def save_meal(data: MealIn, background: BackgroundTasks,
              db: Session = Depends(db_session),
              user: User = Depends(auth.current_user)):
    """Krok 2: zapis posiłku (po ewentualnej korekcie użytkownika)."""
    background.add_task(maybe_sync, user.id)
    meal = Meal(
        user_id=user.id,
        date=data.date,
        time=(datetime.strptime(data.time, "%H:%M").time() if data.time
              else user_time(db.get(UserProfile, user.id))),
        description=data.description,
        photo_path=data.photo_path,
        kcal=round(data.kcal),
        kcal_min=round(data.kcal_min) if data.kcal_min else None,
        kcal_max=round(data.kcal_max) if data.kcal_max else None,
        protein_g=data.protein_g,
        fat_g=data.fat_g,
        carbs_g=data.carbs_g,
        fiber_g=data.fiber_g,
        sugars_g=data.sugars_g,
        items_json=json.dumps(data.items, ensure_ascii=False) if data.items else None,
        assumptions_json=json.dumps(data.assumptions, ensure_ascii=False) if data.assumptions else None,
        source=data.source,
    )
    db.add(meal)
    db.commit()
    if data.source in ("photo", "text", "manual", "saved"):
        usage_service.bump(db, user.id, f"meal_save_{data.source}")
    return {"id": meal.id}


@router.delete("/api/meals/{meal_id}")
def delete_meal(meal_id: int, db: Session = Depends(db_session),
                user: User = Depends(auth.current_user)):
    meal = db.get(Meal, meal_id)
    if meal is None or meal.user_id != user.id:
        raise HTTPException(404)
    db.delete(meal)
    db.commit()
    usage_service.bump(db, user.id, "meal_delete")
    return {"ok": True}


@router.delete("/api/queue/{pending_id}")
def delete_pending(pending_id: int, db: Session = Depends(db_session),
                   user: User = Depends(auth.current_user)):
    """Usunięcie wpisu z kolejki offline (bez przetwarzania przez LLM)."""
    pending = db.get(PendingMeal, pending_id)
    if pending is None or pending.user_id != user.id:
        raise HTTPException(404)
    meal_queue.delete_pending(db, pending)
    usage_service.bump(db, user.id, "queue_delete")
    return {"ok": True}


@router.post("/api/queue/process")
def queue_process(background: BackgroundTasks, db: Session = Depends(db_session),
                  user: User = Depends(auth.current_user)):
    usage_service.bump(db, user.id, "queue_process")
    background.add_task(meal_queue.process_queue, user.id)
    return {"ok": True}


# ── Moje posiłki (zapisane szablony) ─────────────────────────────────────

class SavedMealIn(BaseModel):
    name: str
    kcal: float
    kcal_min: float | None = None
    kcal_max: float | None = None
    protein_g: float = 0
    fat_g: float = 0
    carbs_g: float = 0
    fiber_g: float = 0
    sugars_g: float = 0
    items: list | None = None
    assumptions: list | None = None


@router.get("/api/saved-meals")
def get_saved_meals(db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    meals = db.scalars(
        select(SavedMeal).where(SavedMeal.user_id == user.id)
        .order_by(SavedMeal.last_used_at.desc())
    ).all()
    return [
        {"id": m.id, "name": m.name, "kcal": m.kcal,
         "kcal_min": m.kcal_min, "kcal_max": m.kcal_max,
         "protein_g": m.protein_g, "fat_g": m.fat_g, "carbs_g": m.carbs_g,
         "fiber_g": m.fiber_g, "sugars_g": m.sugars_g}
        for m in meals
    ]


@router.post("/api/saved-meals", status_code=201)
def create_saved_meal(data: SavedMealIn, db: Session = Depends(db_session),
                      user: User = Depends(auth.current_user)):
    """Upsert po nazwie: zapis pod istniejącą nazwą nadpisuje wartości
    zamiast tworzyć duplikat (import w transfer.py deduplikuje tak samo)."""
    name = data.name.strip()
    sm = db.scalar(
        select(SavedMeal).where(SavedMeal.user_id == user.id, SavedMeal.name == name)
    )
    if sm is None:
        sm = SavedMeal(user_id=user.id, name=name)
        db.add(sm)
    sm.kcal = round(data.kcal)
    sm.kcal_min = round(data.kcal_min) if data.kcal_min else None
    sm.kcal_max = round(data.kcal_max) if data.kcal_max else None
    sm.protein_g = data.protein_g
    sm.fat_g = data.fat_g
    sm.carbs_g = data.carbs_g
    sm.fiber_g = data.fiber_g
    sm.sugars_g = data.sugars_g
    sm.items_json = json.dumps(data.items, ensure_ascii=False) if data.items else None
    sm.assumptions_json = json.dumps(data.assumptions, ensure_ascii=False) if data.assumptions else None
    sm.last_used_at = datetime.utcnow()
    db.commit()
    usage_service.bump(db, user.id, "saved_meal_create")
    return {"id": sm.id}


@router.delete("/api/saved-meals/{meal_id}")
def delete_saved_meal(meal_id: int, db: Session = Depends(db_session),
                      user: User = Depends(auth.current_user)):
    sm = db.get(SavedMeal, meal_id)
    if sm is None or sm.user_id != user.id:
        raise HTTPException(404)
    db.delete(sm)
    db.commit()
    return {"ok": True}


@router.post("/api/saved-meals/{meal_id}/use")
def use_saved_meal(meal_id: int, db: Session = Depends(db_session),
                   user: User = Depends(auth.current_user)):
    sm = db.get(SavedMeal, meal_id)
    if sm is None or sm.user_id != user.id:
        raise HTTPException(404)
    sm.last_used_at = datetime.utcnow()
    db.commit()
    usage_service.bump(db, user.id, "saved_meal_use")
    return {
        "description": sm.name,
        "kcal": sm.kcal, "kcal_min": sm.kcal_min, "kcal_max": sm.kcal_max,
        "protein_g": sm.protein_g, "fat_g": sm.fat_g, "carbs_g": sm.carbs_g,
        "fiber_g": sm.fiber_g, "sugars_g": sm.sugars_g,
        "items": json.loads(sm.items_json) if sm.items_json else [],
        "assumptions": json.loads(sm.assumptions_json) if sm.assumptions_json else [],
    }
