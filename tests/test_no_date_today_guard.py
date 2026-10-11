"""Strażnik: testy z `TestClient` nie wołają `date.today()` (strefa PROCESU =
UTC na runnerze GitHuba), tylko `app_today()` z conftest — inaczej między 22:00
a 24:00 UTC rozjeżdżają się z serwerem (czerwony CI 2026-09-05). Świadome
wyjątki (np. statystyki admina liczone dniem serwera) oznacz komentarzem
`# dzień serwera` w tej samej linii."""
import re
from pathlib import Path

TESTS = Path(__file__).parent
EXEMPT_FILES = {"test_timezone.py", "conftest.py", "test_no_date_today_guard.py"}


def test_testclient_tests_use_app_today_not_date_today():
    offenders = []
    for path in sorted(TESTS.glob("*.py")):
        if path.name in EXEMPT_FILES:
            continue
        text = path.read_text()
        if "TestClient" not in text:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"\bdate\.today\(\)", line) and "# dzień serwera" not in line:
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "użyj app_today() (tests/conftest.py):\n" + "\n".join(offenders)
