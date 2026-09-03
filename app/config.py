import os
from datetime import date
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

# Tokeny sesji Garmina żyją poza drzewem repo (katalog bazowy — per user podkatalog).
GARMIN_TOKENS_DIR = Path(
    os.path.expanduser(os.getenv("GARMINTOKENS", "~/.fit-krasnal/garth"))
)

# Sesja logowania (podpisane ciasteczko). W produkcji MUSI być ustawione własne
# FIT_KRASNAL_SECRET_KEY — domyślna wartość jest jawnie oznaczona jako niebezpieczna,
# żeby nie dało się jej przeoczyć w konfiguracji wdrożenia.
DEV_SECRET_KEY = "dev-insecure-secret-change-me"
SECRET_KEY = os.getenv("FIT_KRASNAL_SECRET_KEY", DEV_SECRET_KEY)
# Tryb dev: ciasteczko bez wymogu HTTPS (localhost). W produkcji zostaw wyłączone.
DEBUG = os.getenv("FIT_KRASNAL_DEBUG", "").lower() in ("1", "true", "yes")
# Wspólny kod zaproszenia do rejestracji. Bez niego rejestracja jest wyłączona.
INVITE_CODE = os.getenv("FIT_KRASNAL_INVITE_CODE", "")

# Klucz szyfrujący sekretów użytkownika (klucze LLM, tokeny Garmina) — Fernet.
# Osobna zmienna od FIT_KRASNAL_SECRET_KEY: rotacja klucza sesji nie może
# unieważniać cudzych kluczy API. Wygeneruj:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENC_KEY = os.getenv("FIT_KRASNAL_ENC_KEY")

# Backend LLM do szacowania posiłków: auto | claude | gemini
# auto = gemini, jeśli jest GEMINI_API_KEY/GOOGLE_API_KEY; w przeciwnym razie claude.
LLM_BACKEND = os.getenv("FIT_KRASNAL_LLM", "auto")
VISION_MODEL = os.getenv("FIT_KRASNAL_VISION_MODEL", "claude-opus-5")
GEMINI_MODEL = os.getenv("FIT_KRASNAL_GEMINI_MODEL", "gemini-3.5-flash")

MAX_PHOTO_BYTES = 15 * 1024 * 1024

# Pseudonimizacja statystyk użycia (plan „Statystyki użycia") — sól HMAC do
# hashowania user_id na pseudonim w tabeli UsageDaily. Stała: zmiana zrywa
# ciągłość statystyk (ten sam user dostanie inny pseudonim). W dev pochodna
# SECRET_KEY (wzorzec jak w app/services/crypto.py), na produkcji WYMAGANA.
USAGE_SALT = os.getenv("FIT_KRASNAL_USAGE_SALT")

# E-mail administratora — jedyne konto z dostępem do /usage. Nie-admin dostaje
# 404 (nie 403 — nie ma po co ogłaszać, że taki widok istnieje).
ADMIN_EMAIL = os.getenv("FIT_KRASNAL_ADMIN_EMAIL", "krasnal@krasnal.cc")

# RODO: wersja noty informacyjnej (/prywatnosc) i zgody na LLM. Zmiana wersji
# unieważnia istniejące zgody (consent.has_consent porównuje wersje) — bumpować
# tylko przy realnej zmianie treści noty, nie przy każdej literówce.
PRIVACY_VERSION = os.getenv("FIT_KRASNAL_PRIVACY_VERSION", "2026-09-03")
# Termin dla istniejących testerów (baner, potem bramka) — data wdrożenia + 14 dni.
CONSENT_DEADLINE = date(2026, 9, 17)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    # Higiena plików (plan „Szyfrowanie sekretów") — DATA_DIR/PHOTOS_DIR tylko
    # dla właściciela procesu; nie na Windows (chmod tam nie ma sensu).
    if os.name == "posix":
        DATA_DIR.chmod(0o700)
        PHOTOS_DIR.chmod(0o700)
