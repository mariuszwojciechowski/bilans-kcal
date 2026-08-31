import io
from datetime import datetime

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import SavedMeal, User


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    u1 = User(email="a@a")
    u2 = User(email="b@b")
    session.add_all([u1, u2])
    session.commit()
    yield session
    session.close()


def _saved(db, user_id, name="Jajecznica"):
    sm = SavedMeal(user_id=user_id, name=name, kcal=250, protein_g=15, fat_g=18, carbs_g=2)
    db.add(sm)
    db.commit()
    return sm


def test_save_and_list(db):
    _saved(db, 1, "Owsianka")
    _saved(db, 1, "Jajecznica")
    meals = db.scalars(select(SavedMeal).where(SavedMeal.user_id == 1)).all()
    assert len(meals) == 2
    assert {m.name for m in meals} == {"Owsianka", "Jajecznica"}


def test_user_isolation(db):
    _saved(db, 1, "Sekrety usera 1")
    meals_u2 = db.scalars(select(SavedMeal).where(SavedMeal.user_id == 2)).all()
    assert len(meals_u2) == 0


def test_use_updates_last_used_at(db):
    sm = _saved(db, 1)
    original_ts = sm.last_used_at
    import time; time.sleep(0.01)
    sm.last_used_at = datetime.utcnow()
    db.commit()
    db.refresh(sm)
    assert sm.last_used_at > original_ts


def test_delete_removes_only_own(db):
    sm1 = _saved(db, 1, "Mój posiłek")
    sm2 = _saved(db, 2, "Posiłek innego")
    db.delete(sm1)
    db.commit()
    assert db.get(SavedMeal, sm1.id) is None
    assert db.get(SavedMeal, sm2.id) is not None
