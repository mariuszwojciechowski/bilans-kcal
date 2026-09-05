"""Granica dnia w strefie czasowej użytkownika — WYMAGANIA.md 8.3.

`user_profile.tz` było zapisywane, ale nieczytane: wszystkie granice dnia
brały się z zegara procesu (`date.today()`), czyli ze strefy serwera (VM w
GCP). Ten moduł jest jedynym miejscem, które zamienia `UserProfile` na
„która jest teraz godzina/dzień u tego użytkownika" — routery i serwisy mają
przez niego przechodzić zamiast wołać `date.today()`/`datetime.now()` wprost.

Znaczniki czasu w bazie zostają w UTC (`sync_ts`, `created_at`,
`last_used_at`) — zmienia się WYŁĄCZNIE wyliczanie daty/godziny dnia.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import UserProfile

DEFAULT_TZ = "Europe/Warsaw"


def user_tz(profile: UserProfile | None) -> ZoneInfo:
    """Strefa czasowa profilu; brak profilu albo nieznana/pusta strefa →
    `DEFAULT_TZ` (dotychczasowy efektywny default aplikacji)."""
    name = profile.tz if profile and profile.tz else DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TZ)


def user_now(profile: UserProfile | None) -> datetime:
    """Bieżący moment w strefie użytkownika (aware)."""
    return datetime.now(user_tz(profile))


def user_today(profile: UserProfile | None) -> date:
    """Dzisiejsza data w strefie użytkownika — granica dnia dla `complete`,
    domyślnego dnia posiłku/aktywności, eksportu, trendów."""
    return user_now(profile).date()


def user_time(profile: UserProfile | None) -> time:
    """Bieżąca godzina (bez daty) w strefie użytkownika — do znaczników
    czasu w ciągu dnia (godzina wpisu posiłku)."""
    return user_now(profile).time()
