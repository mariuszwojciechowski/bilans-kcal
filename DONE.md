# Zrobione — indeks

Spis zrealizowanych punktów z [TODO.md](TODO.md). Trzymamy je zamiast kasować:
każdy wpis mówi, CO było problemem i JAKĄ decyzję podjęto — to bywa potrzebne,
gdy temat wraca. **Pełne wpisy leżą w `archive/`**, tutaj są tylko tytuły.

**Jak czytać:** znajdź tytuł na liście → wyciągnij jego sekcję z pliku archiwum,
nie czytaj całego pliku:
`awk '/^## <fragment tytułu>/,/^## /' archive/done-v24-v25.md`.
Szukanie po treści: `grep -rn "<fraza>" archive/`.

**Nowy wpis** dopisuj na początku właściwej listy poniżej, a pełną treść na
początek odpowiedniego pliku w `archive/` (najnowsze u góry). Format wpisu
w archiwum: tytuł + **maksymalnie 5 punktów**; szczegóły implementacji zostają
w komunikacie commita, nie tutaj.

## v24–v25 — [archive/done-v24-v25.md](archive/done-v24-v25.md)

- Integracja ze Strava — dla użytkowników bez Garmina (25.0.0, e102d2f)
- Prognoza doby: spoczynek z historii Garmina zamiast Mifflina (24.9.2)
- Cel dnia z prognozy pełnej doby + roszady na „Dziś" (24.4.0 f0f7080, 24.5.0 1f4d59d, 24.6.0)
- Podmiana ikony krasnala z prawdziwej grafiki 24×24 (24.3.5)
- Testy: „dziś" ze strefy użytkownika, nie zegara runnera — naprawa czerwonego CI (24.3.1)
- Ikona krasnala przy komunikatach (24.3.0, b70803e)
- Cel białka zależny od bilansu (redukcja / masa) (24.2.0, 572314c) — WYMAGANIA.md §10.2
- Bilans zamiast deficytu w Ustawieniach + jawny „cel dnia" (24.1.0, 6096340)
- Tabela MET jako dane, nie kod (24.0.0) — WYMAGANIA.md §4

## v21–v23 — [archive/done-v21-v23.md](archive/done-v21-v23.md)

- Strefa czasowa użytkownika jako granica dnia (23.0.0) — WYMAGANIA.md 8.3
- Statystyki: obserwowalność poprawki kcal (21.5.0) i kalibracji adaptacyjnej (22.0.0) — (22.2.0)
- Zakres statystyk `/usage`: testerzy / wszyscy / tylko ja (22.1.0)
- Kalibracja adaptacyjna (22.0.0, 30d4e71)
- Poprawa wyliczania kcal na dzień w toku (21.5.0, 30d4e71)
- Trendy liczą kcal inaczej niż „Dziś" — jedna logika wydatku w całej aplikacji (21.4.0)

## Multi-user, RODO, refaktory — [archive/done-multiuser-rodo.md](archive/done-multiuser-rodo.md)

- Cztery poprawki UX w widoku mobilnym: zapis wagi, czyszczenie i odświeżanie formularza „Dodaj"
- Implementacja zgubionej funkcjonalności
- Duplikat trendów i `day_report` w routerze — wyniesienie do serwisów (a4aa213)
- Stara wersja na GitHub Pages — wyłączenie i sprzątanie po niej (d8833e3)
- Statystyki użycia — dopracowanie po zgłoszeniach (ae065c8, eb1f1a7, f300e98)
- Statystyki użycia — adopcja i najczęściej klikane opcje (be997a0)
- Prognoza osiągnięcia celu ciężaru (ed1cb9d) — WYMAGANIA.md 6.4
- Szyfrowanie sekretów użytkownika: klucze LLM i tokeny Garmina (c1e1c9b, 7b4a88d)
- RODO: informacja, zgoda na wysyłkę zdjęć do LLM, retencja (96fb708)
- Rok urodzenia zamiast pełnej daty — minimalizacja danych (aba6c7f)

## Zakładka Aktywności i szlify UI — [archive/done-aktywnosci.md](archive/done-aktywnosci.md)

- Ujednolicenie nawigacji desktop ↔ mobile
- Przemeblowanie: równanie do Bilansu, karta GARMIN w zakładce, dwie kolumny (02cc6f2)
- Przycisk „Aktywności/Kroki" — wyrównanie, podejście trzecie (02cc6f2)
- Skala intensywności w nowej linii (02cc6f2)
- Szlif zakładki Aktywności — runda 2 po testach właściciela (443cb0b)
- Rozbicie wydatku: pomiar Garmina jako suma, kroki jako reszta (db4f6cf)
- Poprawki zakładki Aktywności po testach na produkcji (aa623ca)
- PILNE: naprawa testów aktywności — deploy zablokowany (7400edf)
- PILNE: naprawa dodania aktywności — produkcja zwraca 500 (1a3401d; kroki 2–3 i 8 NIE zrobione)

## MVP: posiłki, widoki mobilne, PWA — [archive/done-mvp.md](archive/done-mvp.md)

- Landing page — drobne poprawki (3c99a77)
- Edytowanie liczby kroków w wersji desktopowej — nieaktualne, jeden widok (d5bb8e8)
- Zmniejszanie zdjęcia w przeglądarce przed wysłaniem na serwer (b30b1eb)
- Redirect po zalogowaniu w zależności od urządzenia — nieaktualne, jeden widok (d5bb8e8)
- Widok Ustawienia w wersji mobilnej (1e3360e)
- Widok Trendy w wersji mobilnej (1e3360e)
- Ręczne dodawanie posiłku (bez szacowania) (b30b1eb, 2485da5)
- Ręczny wpis aktywności + zakładka Aktywności/Kroki (1aad080)
- Dashboard lepiej wyglądający na telefonie — jeden widok responsive (d5bb8e8)
- Instalowanie na ekranie głównym telefonu (1e3360e)
- Moje posiłki — zapamiętane, jednym kliknięciem — WYMAGANIA.md 5.2
- Konwersja HEIC — zdjęcia z iPhone'ów — WYMAGANIA.md 5.1
