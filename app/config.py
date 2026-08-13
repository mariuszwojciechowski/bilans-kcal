import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Wczytuje BASE_DIR/.env do środowiska (bez nadpisywania istniejących zmiennych).
    Plik .env jest w .gitignore — to lokalne miejsce na sekrety (klucze API)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Wszystkie dane runtime (baza, zdjęcia) trafiają do data/ — katalog jest w .gitignore,
# bo repo jest publiczne, a to dane prywatne użytkownika.
DATA_DIR = Path(os.getenv("FIT_KRASNAL_DATA", BASE_DIR / "data"))
PHOTOS_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "fit-krasnal.db"

# Tokeny sesji Garmina żyją poza drzewem repo.
GARMIN_TOKENS_DIR = Path(
    os.path.expanduser(os.getenv("GARMINTOKENS", "~/.fit-krasnal/garth"))
)

# Backend LLM do szacowania posiłków: auto | claude | gemini
# auto = gemini, jeśli jest GEMINI_API_KEY/GOOGLE_API_KEY; w przeciwnym razie claude.
LLM_BACKEND = os.getenv("FIT_KRASNAL_LLM", "auto")
VISION_MODEL = os.getenv("FIT_KRASNAL_VISION_MODEL", "claude-opus-5")
GEMINI_MODEL = os.getenv("FIT_KRASNAL_GEMINI_MODEL", "gemini-3.5-flash")

MAX_PHOTO_BYTES = 15 * 1024 * 1024


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
