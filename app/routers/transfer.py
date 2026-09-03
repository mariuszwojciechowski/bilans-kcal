"""Przenoszenie danych między urządzeniami (eksport/import pliku JSON)."""
import json
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import auth
from ..db import db_session
from ..models import User
from ..services import meal_queue, transfer
from ..services import usage as usage_service

router = APIRouter()


@router.get("/api/transfer/export")
def transfer_export(db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    """'Przygotuj dane do przeniesienia na inne urządzenie' — plik JSON do pobrania."""
    payload = transfer.export_payload(db, user.id)
    usage_service.bump(db, user.id, "transfer_export")
    return Response(
        json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename="fit-krasnal-{date.today().isoformat()}.json"'},
    )


@router.post("/api/transfer/import")
async def transfer_import(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """'Wczytaj dane z innego urządzenia' — scala plik transferu (desktop lub telefon)."""
    try:
        payload = json.loads(await file.read())
        counts = transfer.import_payload(db, user.id, payload)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"Nieprawidłowy plik transferu: {exc}")
    usage_service.bump(db, user.id, "transfer_import")
    background.add_task(meal_queue.process_queue, user.id)
    return counts
