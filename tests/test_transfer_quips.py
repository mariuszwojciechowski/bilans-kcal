from datetime import date, time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Meal, PendingMeal, User, UserProfile, WeightLog
from app.services import meal_queue, quips, transfer


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(meal_queue, "PHOTOS_DIR", tmp_path / "photos")
    monkeypatch.setattr(transfer, "PHOTOS_DIR", tmp_path / "photos")
    session.add(User(email="t@t"))
    session.commit()
    yield session
    session.close()


def _seed(db):
    db.add(UserProfile(user_id=1, birth_date=date(1980, 6, 15), sex="M", height_cm=180))
    db.add(WeightLog(user_id=1, date=date(2026, 8, 10), weight_kg=80.5))
    db.add(Meal(user_id=1, date=date(2026, 8, 12), time=time(12, 30),
                description="jajecznica", kcal=420, protein_g=25, fat_g=30, carbs_g=12))
    db.commit()


def test_transfer_roundtrip_idempotent(db):
    _seed(db)
    payload = transfer.export_payload(db, 1)
    assert payload["format"] == "fit-krasnal-transfer"
    assert len(payload["meals"]) == 1 and len(payload["weights"]) == 1

    counts = transfer.import_payload(db, 1, payload)  # import własnego eksportu
    assert counts["meals"] == 0 and counts["weights"] == 0  # same duplikaty
    assert counts["skipped"] == 2
    assert len(db.scalars(select(Meal)).all()) == 1


def test_transfer_import_mobile_pending(db):
    _seed(db)
    mobile = {
        "format": "fit-krasnal-transfer", "version": 1, "source": "mobile",
        "pending": [
            {"date": "2026-08-20", "time": "13:15", "description": "pizza na plaży",
             "note": None, "photo_b64": None},
        ],
    }
    counts = transfer.import_payload(db, 1, mobile)
    assert counts["pending"] == 1
    row = db.scalars(select(PendingMeal)).one()
    assert row.date == date(2026, 8, 20) and row.time == time(13, 15)


def test_transfer_rejects_foreign_file(db):
    with pytest.raises(ValueError):
        transfer.import_payload(db, 1, {"format": "cos-innego"})


def _macros(protein="ok", fiber="ok", sugars="ok"):
    return {"protein": {"status": protein}, "fiber": {"status": fiber},
            "sugars": {"status": sugars}}


def test_quips_priorities():
    assert quips.pick_category(0, 2000, -500, _macros()) == "empty"
    assert quips.pick_category(1800, 2000, -200, _macros(sugars="above")) == "sugar_high"
    assert quips.pick_category(1500, 2000, -200, _macros(protein="below")) == "protein_low"
    assert quips.pick_category(1800, 2000, -100, _macros(fiber="below")) == "fiber_low"
    assert quips.pick_category(2600, 2000, 300, _macros()) == "over"
    assert quips.pick_category(700, 2000, -1500, _macros()) == "under"
    assert quips.pick_category(1700, 2000, -400, _macros()) == "ontrack"


def test_quips_goal_categories():
    assert quips.goal_category(-0.5) == "goal_reached"
    assert quips.goal_category(1.5) == "goal_close"
    assert quips.goal_category(8.0) == "goal_far"


def test_quips_goal_reached_always_wins_and_diff_substituted():
    text = quips.pick(1700, 2000, -400, _macros(), weight_to_goal_kg=-0.3)
    assert any(text == t for t in quips._quips()["goal_reached"])
    close = quips._quips()["goal_close"] + quips._quips()["goal_far"]
    for _ in range(20):
        t = quips.pick(1700, 2000, -400, _macros(), weight_to_goal_kg=5.2)
        assert "{diff}" not in t
        if "5.2" in t:
            assert any("{diff}" in c for c in close)
            break


def test_quips_texts_exist_for_all_categories():
    for cat in ("under", "over", "ontrack", "protein_low", "fiber_low", "sugar_high", "empty"):
        text = quips.pick(0, 0, 0, _macros()) if cat == "empty" else None
        assert quips._quips()[cat], cat
        if text:
            assert isinstance(text, str) and len(text) > 10


def test_quips_film_references_present():
    all_quips = quips._quips()
    assert any("Chłopaki nie płaczą" in t for cat in all_quips.values() for t in cat)
    assert any("Kiedy wchodzisz między wrony" in t for cat in all_quips.values() for t in cat)
    assert any("Pieniądze to nie wszystko" in t for cat in all_quips.values() for t in cat)


def test_quips_more_film_quotes_present():
    all_quips = quips._quips()
    flat = [t for cat in all_quips.values() for t in cat]
    assert any("Wiosna, panie sierżancie" in t for t in flat)
    assert any("Royale z serem" in t for t in flat)
    assert any("Dżizus, kurwa, ja pierdolę" in t for t in flat)
    assert any("Wyrwałem chwasta" in t for t in flat)


def test_quips_goal_texts_all_have_diff_placeholder():
    for cat in ("goal_close", "goal_far"):
        for text in quips._quips()[cat]:
            assert "{diff}" in text, text
