"""Profil użytkownika i ręczna synchronizacja Garmin."""
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth
from ..db import db_session
from ..models import User, UserProfile
from ..providers.garmin import GarminNotLoggedIn, GarminProvider
from ..services import usage as usage_service
from ..services.macros import lifestyle_options
from ..services.sync import mark_attempt, sync_range

router = APIRouter()


# ── Profil ────────────────────────────────────────────────────────────────

class ProfileIn(BaseModel):
    birth_year: int | None = None
    birth_date: date | None = None  # wejście zgodnościowe: stary klient/plik transferu
    sex: str  # 'M' | 'F'
    height_cm: float
    target_deficit_kcal: int = 500
    target_weight_kg: float | None = None  # cel ciężaru
    lifestyle: str = "active"
    tz: str = "Europe/Warsaw"


MIN_BIRTH_YEAR_AGE = 13
MAX_BIRTH_YEAR_AGE = 120


def _resolve_birth_year(data: "ProfileIn") -> int:
    birth_year = data.birth_year
    if birth_year is None and data.birth_date is not None:
        birth_year = data.birth_date.year
    if birth_year is None:
        raise HTTPException(422, "Podaj rok urodzenia")
    this_year = date.today().year
    if not (this_year - MAX_BIRTH_YEAR_AGE <= birth_year <= this_year - MIN_BIRTH_YEAR_AGE):
        raise HTTPException(422, "Rok urodzenia poza sensownym zakresem")
    return birth_year


class ProfileOut(BaseModel):
    birth_year: int | None
    sex: str
    height_cm: float
    target_deficit_kcal: int
    target_weight_kg: float | None
    lifestyle: str
    tz: str


@router.get("/api/profile", response_model=ProfileOut)
def get_profile(db: Session = Depends(db_session), user: User = Depends(auth.current_user)):
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(404, "Profil nie jest jeszcze skonfigurowany")
    return profile


@router.put("/api/profile")
def put_profile(data: ProfileIn, db: Session = Depends(db_session),
                user: User = Depends(auth.current_user)):
    if data.sex.upper() not in ("M", "F"):
        raise HTTPException(422, "sex musi być 'M' lub 'F'")
    birth_year = _resolve_birth_year(data)
    birth_date = date(birth_year, 7, 1)
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id, birth_date=birth_date, birth_year=birth_year,
                              sex=data.sex.upper(), height_cm=data.height_cm)
        db.add(profile)
    profile.birth_date = birth_date
    profile.birth_year = birth_year
    profile.sex = data.sex.upper()
    profile.height_cm = data.height_cm
    profile.target_deficit_kcal = data.target_deficit_kcal
    if data.target_weight_kg is not None:
        profile.target_weight_kg = data.target_weight_kg
    if data.lifestyle in lifestyle_options():
        profile.lifestyle = data.lifestyle
    profile.tz = data.tz
    db.commit()
    usage_service.bump(db, user.id, "profile_save")
    return {"ok": True}


@router.post("/profile-form")
def profile_form(
    birth_year: int = Form(...),
    sex: str = Form(...),
    height_cm: float = Form(...),
    target_deficit_kcal: int = Form(500),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    put_profile(
        ProfileIn(birth_year=birth_year, sex=sex, height_cm=height_cm,
                  target_deficit_kcal=target_deficit_kcal),
        db,
        user,
    )
    return RedirectResponse("/", status_code=303)


# ── Synchronizacja Garmin ─────────────────────────────────────────────────

@router.post("/api/sync")
def sync(days: int = 7, db: Session = Depends(db_session),
         user: User = Depends(auth.current_user)):
    """Ręczna synchronizacja — bez throttla, synchronicznie, zwraca liczniki."""
    mark_attempt(user.id)
    usage_service.bump(db, user.id, "sync_manual")
    try:
        return sync_range(db, GarminProvider(user.id, db), user.id, days=days)
    except GarminNotLoggedIn as exc:
        raise HTTPException(409, str(exc))
