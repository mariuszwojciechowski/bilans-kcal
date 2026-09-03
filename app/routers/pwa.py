"""PWA — pliki publiczne (bez auth): manifest i service worker."""
from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..deps import STATIC_DIR

router = APIRouter()


@router.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@router.get("/sw.js")
def pwa_sw():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})
