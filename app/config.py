import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Wszystkie dane runtime (baza, zdjęcia) trafiają do data/ — katalog jest w .gitignore,
# bo repo jest publiczne, a to dane prywatne użytkownika.
DATA_DIR = Path(os.getenv("FIT_KRASNAL_DATA", BASE_DIR / "data"))
PHOTOS_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "fit-krasnal.db"

# Tokeny sesji Garmina żyją poza drzewem repo.
GARMIN_TOKENS_DIR = Path(
    os.path.expanduser(os.getenv("GARMINTOKENS", "~/.fit-krasnal/garth"))
)

VISION_MODEL = os.getenv("FIT_KRASNAL_VISION_MODEL", "claude-opus-5")

MAX_PHOTO_BYTES = 15 * 1024 * 1024


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
