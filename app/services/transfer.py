"""Przenoszenie danych między urządzeniami (M10).

Format pliku: JSON `fit-krasnal-transfer` v1. Ten sam plik obsługuje:
- eksport z desktopa (profil, wagi, posiłki, kolejka) -> inne stanowisko,
- eksport ze strony mobilnej (tylko kolejka: opisy + zdjęcia base64) -> desktop.
Nośnikiem może być cokolwiek (Google Drive, mail, kabel) — to zwykły plik.
Import jest idempotentny: wagi dedupowane po dacie, posiłki po stabilnym
external_id (wielokrotne wczytanie tego samego pliku nie duplikuje posiłków;
posiłki bez external_id — starsze eksporty — nie mają z czym się dopasować
i są wczytywane jako nowe, czyli faktycznie duplikowane)."""

import base64
import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PHOTOS_DIR
from ..models import Activity, Meal, PendingMeal, SavedMeal, UserProfile, WeightLog
from . import meal_queue

FORMAT = "fit-krasnal-transfer"
VERSION = 1


def _t(value: time | None) -> str | None:
    return value.isoformat() if value else None


def export_payload(db: Session, user_id: int) -> dict:
    profile = db.get(UserProfile, user_id)
    weights = db.scalars(select(WeightLog).where(WeightLog.user_id == user_id)).all()
    meals = db.scalars(select(Meal).where(Meal.user_id == user_id)).all()
    pending = db.scalars(select(PendingMeal).where(PendingMeal.user_id == user_id)).all()

    pending_out = []
    for p in pending:
        photo_b64 = None
        if p.photo_path and (PHOTOS_DIR / p.photo_path).exists():
            photo_b64 = base64.b64encode((PHOTOS_DIR / p.photo_path).read_bytes()).decode()
        pending_out.append({
            "date": p.date.isoformat(), "time": _t(p.time),
            "description": p.description, "note": p.note, "photo_b64": photo_b64,
        })

    return {
        "format": FORMAT,
        "version": VERSION,
        "source": "desktop",
        "exported_at": datetime.utcnow().isoformat(),
        "profile": {
            "birth_year": profile.birth_year,
            "sex": profile.sex,
            "height_cm": profile.height_cm,
            "target_deficit_kcal": profile.target_deficit_kcal,
            "target_weight_kg": profile.target_weight_kg,
            "lifestyle": profile.lifestyle or "active",
            "last_weight_kg": (
                max(weights, key=lambda w: w.date).weight_kg if weights else None
            ),
            "tz": profile.tz,
        } if profile else None,
        "weights": [
            {"date": w.date.isoformat(), "weight_kg": w.weight_kg, "source": w.source}
            for w in weights
        ],
        "meals": [
            {
                "external_id": m.external_id,
                "date": m.date.isoformat(), "time": _t(m.time),
                "description": m.description, "kcal": m.kcal,
                "kcal_min": m.kcal_min, "kcal_max": m.kcal_max,
                "protein_g": m.protein_g, "fat_g": m.fat_g, "carbs_g": m.carbs_g,
                "fiber_g": m.fiber_g, "sugars_g": m.sugars_g,
                "items_json": m.items_json, "assumptions_json": m.assumptions_json,
                "source": m.source,
            }
            for m in meals
        ],
        "pending": pending_out,
        "saved_meals": [
            {"name": m.name, "kcal": m.kcal,
             "kcal_min": m.kcal_min, "kcal_max": m.kcal_max,
             "protein_g": m.protein_g, "fat_g": m.fat_g, "carbs_g": m.carbs_g,
             "fiber_g": m.fiber_g, "sugars_g": m.sugars_g,
             "items_json": m.items_json, "assumptions_json": m.assumptions_json}
            for m in db.scalars(select(SavedMeal).where(SavedMeal.user_id == user_id)).all()
        ],
        "activities": [
            {"garmin_id": a.garmin_id,
             "date": a.date.isoformat(), "type": a.type,
             "duration_s": a.duration_s, "distance_m": a.distance_m,
             "kcal_garmin": a.kcal_garmin}
            for a in db.scalars(select(Activity).where(
                Activity.user_id == user_id, Activity.source == "manual"
            )).all()
        ],
    }


def _parse_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def import_payload(db: Session, user_id: int, payload: dict) -> dict:
    if payload.get("format") != FORMAT:
        raise ValueError("To nie jest plik transferu Fit Krasnal.")
    if payload.get("version", 0) > VERSION:
        raise ValueError("Plik pochodzi z nowszej wersji aplikacji — zaktualizuj ją.")

    counts = {"meals": 0, "weights": 0, "pending": 0, "profile": 0, "saved_meals": 0, "activities": 0, "skipped": 0}

    if payload.get("profile") and db.get(UserProfile, user_id) is None:
        p = payload["profile"]
        birth_year = p.get("birth_year")
        if birth_year is None and p.get("birth_date"):  # plik z dawniejszej wersji
            birth_year = date.fromisoformat(p["birth_date"]).year
        db.add(UserProfile(user_id=user_id, birth_date=date(birth_year, 7, 1),
                           birth_year=birth_year,
                           sex=p["sex"], height_cm=p["height_cm"],
                           target_deficit_kcal=p.get("target_deficit_kcal", 500),
                           target_weight_kg=p.get("target_weight_kg"),
                           lifestyle=p.get("lifestyle", "active"),
                           tz=p.get("tz", "Europe/Warsaw")))
        counts["profile"] = 1

    for w in payload.get("weights", []):
        day = date.fromisoformat(w["date"])
        exists = db.scalar(select(WeightLog).where(
            WeightLog.user_id == user_id, WeightLog.date == day))
        if exists:
            counts["skipped"] += 1
            continue
        db.add(WeightLog(user_id=user_id, date=day, weight_kg=w["weight_kg"],
                         source=w.get("source", "import")))
        counts["weights"] += 1

    # Dedup po external_id: ten sam posiłek wczytany wielokrotnie (ten sam plik
    # transferu) liczy się tylko raz. Wpisy bez external_id (starsze eksporty,
    # sprzed wprowadzenia identyfikatorów) nie mają z czym się dopasować —
    # zawsze trafiają jako nowe (i dostają świeży external_id).
    existing_ids = {
        eid for (eid,) in db.execute(
            select(Meal.external_id).where(Meal.user_id == user_id)
        ).all()
    }
    for m in payload.get("meals", []):
        eid = m.get("external_id")
        if eid and eid in existing_ids:
            counts["skipped"] += 1
            continue
        db.add(Meal(user_id=user_id, external_id=eid or uuid.uuid4().hex,
                    date=date.fromisoformat(m["date"]),
                    time=_parse_time(m.get("time")), description=m.get("description", ""),
                    kcal=round(m["kcal"]), kcal_min=m.get("kcal_min"), kcal_max=m.get("kcal_max"),
                    protein_g=m.get("protein_g", 0), fat_g=m.get("fat_g", 0),
                    carbs_g=m.get("carbs_g", 0), fiber_g=m.get("fiber_g", 0),
                    sugars_g=m.get("sugars_g", 0), items_json=m.get("items_json"),
                    assumptions_json=m.get("assumptions_json"),
                    source=m.get("source", "import")))
        if eid:
            existing_ids.add(eid)
        counts["meals"] += 1

    existing_pending = {
        (p.date.isoformat(), _t(p.time), p.description, p.note)
        for p in db.scalars(select(PendingMeal).where(PendingMeal.user_id == user_id)).all()
    }
    for p in payload.get("pending", []):
        key = (p["date"], p.get("time"), p.get("description"), p.get("note"))
        if key in existing_pending:
            counts["skipped"] += 1
            continue
        photo_bytes = base64.b64decode(p["photo_b64"]) if p.get("photo_b64") else None
        meal_queue.enqueue(db, user_id, date.fromisoformat(p["date"]),
                           _parse_time(p.get("time")) or time(12, 0),
                           description=p.get("description"), note=p.get("note"),
                           photo_bytes=photo_bytes)
        counts["pending"] += 1

    existing_saved_names = {
        m.name for m in db.scalars(
            select(SavedMeal).where(SavedMeal.user_id == user_id)
        ).all()
    }
    for m in payload.get("saved_meals", []):
        if m["name"] in existing_saved_names:
            counts["skipped"] += 1
            continue
        db.add(SavedMeal(
            user_id=user_id, name=m["name"], kcal=m["kcal"],
            kcal_min=m.get("kcal_min"), kcal_max=m.get("kcal_max"),
            protein_g=m.get("protein_g", 0), fat_g=m.get("fat_g", 0),
            carbs_g=m.get("carbs_g", 0), fiber_g=m.get("fiber_g", 0),
            sugars_g=m.get("sugars_g", 0),
            items_json=m.get("items_json"), assumptions_json=m.get("assumptions_json"),
        ))
        existing_saved_names.add(m["name"])
        counts["saved_meals"] += 1

    existing_activity_ids = {
        aid for (aid,) in db.execute(
            select(Activity.garmin_id).where(Activity.user_id == user_id, Activity.source == "manual")
        ).all()
    }
    for a in payload.get("activities", []):
        aid = a.get("garmin_id")
        if aid and aid in existing_activity_ids:
            counts["skipped"] += 1
            continue
        db.add(Activity(
            user_id=user_id, garmin_id=aid or ("manual-" + uuid.uuid4().hex),
            date=date.fromisoformat(a["date"]), type=a["type"],
            duration_s=a["duration_s"], distance_m=a.get("distance_m"),
            kcal_garmin=a.get("kcal_garmin"), source="manual"
        ))
        if aid:
            existing_activity_ids.add(aid)
        counts["activities"] += 1

    db.commit()
    # Stan filtru kalibracji nie wchodzi do eksportu (nie ma go w `payload`) —
    # po imporcie przeliczamy go od zera z historii (kilkaset kroków, milisekundy).
    from . import calibration
    calibration.maybe_recalibrate(db, user_id)
    return counts
