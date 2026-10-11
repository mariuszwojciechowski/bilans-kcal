"""Utwardzenie publicznych interfejsów — czyste middleware ASGI, bez nowych
frameworków. Wpinane w `main.py:install_hardening`.

- SecurityHeadersMiddleware: nagłówki bezpieczeństwa + CSP tolerująca
  inline'owe skrypty/style szablonów (jeden plik `mobile.html` z całym JS).
- SameOriginMiddleware: ochrona CSRF dla żądań zmieniających stan — odrzuca
  żądania z obcego origin (Sec-Fetch-Site / Origin / Referer).
- BodyLimitMiddleware: 413 dla zbyt dużych zdjęć po samym `Content-Length`,
  zanim multipart w ogóle zostanie wczytany.
"""
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

CSP = (
    "default-src 'self'; img-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self' https://accounts.google.com"
)


class SecurityHeadersMiddleware:
    def __init__(self, app, hsts: bool) -> None:
        self.app = app
        self.headers = [
            ("x-content-type-options", "nosniff"),
            ("referrer-policy", "same-origin"),
            ("x-frame-options", "DENY"),
            ("permissions-policy", "camera=(self), geolocation=()"),
            ("content-security-policy", CSP),
        ]
        if hsts:   # nie w dev po http — przeglądarka zapamiętałaby HSTS dla localhost
            self.headers.append(
                ("strict-transport-security", "max-age=31536000; includeSubDomains"))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers:
                    if name not in headers:
                        headers.append(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _origin_host(value: str) -> str:
    return urlsplit(value).netloc.lower()


class SameOriginMiddleware:
    """CSRF: żądanie zmieniające stan (nie GET/HEAD/OPTIONS) musi pochodzić
    z tej samej strony.

    1. `Sec-Fetch-Site` obecny i inny niż `same-origin`/`none` → 403.
    2. `Origin` (albo `Referer`, gdy Origin brak) o innym hoście niż `Host` → 403.
    3. Bez żadnego z tych nagłówków (curl, testy, stare klienty) — przepuszczamy;
       ciasteczko sesji jest `SameSite=Lax`, więc obca strona i tak go nie doda.

    Powłoka Android (Capacitor) ładuje stronę z tego samego hosta co API
    (`server.url`), więc jej `fetch` niesie `Origin` = ten host i
    `Sec-Fetch-Site: same-origin` — przechodzi jak zwykła przeglądarka.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            headers = Headers(scope=scope)
            reason = self.rejection(headers)
            if reason:
                response = JSONResponse({"detail": reason}, status_code=403)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)

    @staticmethod
    def rejection(headers: Headers) -> str | None:
        site = headers.get("sec-fetch-site", "").lower()
        if site and site not in ("same-origin", "none"):
            return "Żądanie z obcej strony (Sec-Fetch-Site) — odrzucone."
        source = headers.get("origin") or headers.get("referer")
        if source:
            if _origin_host(source) != headers.get("host", "").lower():
                return "Żądanie z obcego origin — odrzucone."
        return None


class BodyLimitMiddleware:
    """413 po `Content-Length` dla wskazanych ścieżek — zanim FastAPI wczyta
    multipart do pliku tymczasowego. Brak nagłówka (chunked) → przepuszczamy,
    a limit pilnuje wtedy sam endpoint (czyta najwyżej limit+1 bajtów)."""

    def __init__(self, app, limit: int, paths: tuple[str, ...]) -> None:
        self.app = app
        self.limit = limit
        self.paths = paths

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] in self.paths:
            length = Headers(scope=scope).get("content-length")
            if length and length.isdigit() and int(length) > self.limit:
                response = JSONResponse(
                    {"detail": f"Zdjęcie za duże (limit {self.limit // (1024 * 1024)} MB)"},
                    status_code=413)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)
