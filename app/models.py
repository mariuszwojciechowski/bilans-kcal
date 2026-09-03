import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Model danych jest multi-user od początku (decyzja D2) — web MVP używa
# jednego lokalnego użytkownika, ale każda tabela domenowa ma user_id.


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profile"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    # legacy: pochodna birth_year (zawsze 1 lipca), nieczytana przez kod —
    # wiek liczy się z birth_year (minimalizacja danych, patrz CLAUDE.md)
    birth_date: Mapped[date] = mapped_column(Date)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(1))  # 'M' | 'F'
    height_cm: Mapped[float] = mapped_column(Float)
    target_deficit_kcal: Mapped[int] = mapped_column(Integer, default=500)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)  # cel ciężaru
    # styl życia -> zakresy makro (sedentary|active|endurance|strength|pregnant)
    lifestyle: Mapped[str] = mapped_column(String, default="active")
    tz: Mapped[str] = mapped_column(String, default="Europe/Warsaw")


class Consent(Base):
    """Zgoda RODO (dziś jedyny rodzaj: 'llm_photos' — wysyłanie zdjęć/opisów
    posiłków do zewnętrznego LLM). Wersjonowana przez `version` (PRIVACY_VERSION);
    wycofanie to nowy stempel `withdrawn_at`, nie usunięcie wiersza — historia zgód
    ma zostać."""

    __tablename__ = "consent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)


class WeightLog(Base):
    __tablename__ = "weight_log"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String, default="garmin")


class DailySummary(Base):
    __tablename__ = "daily_summary"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kcal_total_garmin: Mapped[int | None] = mapped_column(Integer)
    kcal_active_garmin: Mapped[int | None] = mapped_column(Integer)
    kcal_bmr_garmin: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    sync_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    complete: Mapped[bool] = mapped_column(default=False)


class Activity(Base):
    __tablename__ = "activity"
    __table_args__ = (UniqueConstraint("user_id", "garmin_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    garmin_id: Mapped[str | None] = mapped_column(String)
    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String)  # running | cycling | strength_training | ...
    duration_s: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    kcal_garmin: Mapped[int | None] = mapped_column(Integer)
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String, default="garmin")  # garmin | manual


class AppSetting(Base):
    """Ustawienia per użytkownik (m.in. klucze LLM). MVP: lokalna baza, plaintext."""

    __tablename__ = "app_setting"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class PendingMeal(Base):
    """Posiłek czekający na przetworzenie przez LLM (brak klucza / brak internetu).
    Retencja 21 dni; po przetworzeniu wpis i zdjęcie są kasowane."""

    __tablename__ = "pending_meal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[time | None] = mapped_column(Time)
    description: Mapped[str | None] = mapped_column(Text)   # wariant tekstowy
    note: Mapped[str | None] = mapped_column(String)        # uwaga do zdjęcia
    photo_path: Mapped[str | None] = mapped_column(String)  # wariant zdjęciowy (zredukowany JPEG)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedMeal(Base):
    __tablename__ = "saved_meal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    kcal: Mapped[int] = mapped_column(Integer)
    kcal_min: Mapped[int | None] = mapped_column(Integer)
    kcal_max: Mapped[int | None] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, default=0)
    sugars_g: Mapped[float] = mapped_column(Float, default=0)
    items_json: Mapped[str | None] = mapped_column(Text)
    assumptions_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Meal(Base):
    __tablename__ = "meal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # identyfikator stabilny między urządzeniami/eksportami — pozwala rozpoznać
    # ten sam posiłek przy wielokrotnym wczytaniu tego samego pliku transferu
    external_id: Mapped[str] = mapped_column(String, unique=True, index=True,
                                              default=lambda: uuid.uuid4().hex)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[time | None] = mapped_column(Time)
    description: Mapped[str] = mapped_column(String, default="")
    photo_path: Mapped[str | None] = mapped_column(String)
    kcal: Mapped[int] = mapped_column(Integer)
    kcal_min: Mapped[int | None] = mapped_column(Integer)
    kcal_max: Mapped[int | None] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, default=0)
    sugars_g: Mapped[float] = mapped_column(Float, default=0)
    items_json: Mapped[str | None] = mapped_column(Text)
    assumptions_json: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="photo")  # photo | text | manual
