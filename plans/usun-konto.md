<!-- Plan wyniesiony z TODO.md (indeks). Po realizacji: wpis do DONE.md + archive/, ten plik usuń. -->
# „Usuń moje dane i konto" w Ustawieniach (6/10)

Zastępuje i konsoliduje dwa wcześniejsze punkty tej listy („Kasowanie konta
z 7-dniowym oknem odzyskania" i „Kasowanie danych z konta — czyszczenie
historii"). Wymóg wprost z WYMAGANIA.md 8.3 (prawo do usunięcia) i warunek
wyjścia pilota poza grono znajomych.

**Decyzje (wiążące, wybór właściciela 2026-09-03):** soft-delete z oknem
odzyskania — konto **7 dni**, sama historia **3 dni**. Dane znikają z aplikacji
NATYCHMIAST; przez okno odzyskania administrator potrafi je przywrócić na prośbę
użytkownika; potem kasacja jest bezpowrotna. Użytkownikowi mówimy o tym wprost
(nie udajemy, że dane wyparowały w tej samej sekundzie — to byłoby kłamstwo
wobec RODO i wobec niego).

**Mechanika (wiążąca):** nie filtrujemy zapytań po `deleted_at` w kilkudziesięciu
miejscach. Zamiast tego kasujemy wiersze naprawdę, a przed kasacją zrzucamy je do
pliku kopii w formacie transferu — czyli tym samym, który już umiemy wczytać.
Odzysk = `transfer.import_payload` z tego pliku.

**Kroki dla implementującego LLM:**

1. **Model.** W `app/models.py`: `User.deleted_at: Mapped[datetime | None]`
   (migracja addytywna w `app/db.py:_migrate()`, wzorzec `password_hash`) oraz
   tabela `DeletionRequest(id, user_id, kind, requested_at, purge_after,
   snapshot_path, original_email, done_at)`, `kind` ∈ `{"data", "account"}`
   (nowa tabela — `create_all` ją utworzy, migracja niepotrzebna).
2. **Serwis `app/services/erasure.py`**:
   - `wipe_data(db, user_id) -> DeletionRequest` — zrzuca
     `transfer.export_payload(db, user_id)` do
     `DATA_DIR/trash/<user_id>-<ts>.json` (`chmod 600`, katalog `700`), potem
     kasuje wiersze użytkownika: `Meal`, `PendingMeal` (+ pliki zdjęć przez
     `meal_queue._delete_photo`), `SavedMeal`, `WeightLog`, `DailySummary`,
     `Activity`. Profil i konto ZOSTAJĄ. `purge_after = teraz + 3 dni`.
   - `delete_account(db, user_id)` — to samo, plus: kasuje `UserProfile`,
     `AppSetting` (czyli i klucze LLM, i tokeny Garmina po wdrożeniu planu
     szyfrowania; do tego czasu skasuj też katalog `garmin_tokens_dir(user_id)`),
     ustawia `User.deleted_at`, zapisuje `original_email` w `DeletionRequest`
     i podmienia `user.email` na `deleted+<id>+<oryginał>` — dzięki temu adres
     jest natychmiast wolny (unikat na `user.email`), a tester może założyć konto
     od nowa. `purge_after = teraz + 7 dni`.
   - `purge_due(db, now)` — kasuje pliki kopii, których `purge_after` minął,
     i twardo usuwa wiersze `user` dla `kind="account"`; stempluje `done_at`.
3. **API w `app/routers/auth.py`** (obok pozostałych route'ów konta —
   login/register/logout):
   - `POST /api/account/wipe-data` — body `{password, confirm}`; `confirm` musi
     być dokładnie `"USUWAM"`, hasło sprawdzane `auth.verify_password` (403 przy
     złym — to jedyna bariera przed kliknięciem z cudzej, niezablokowanej
     przeglądarki); zwraca liczniki skasowanych wierszy.
   - `POST /api/account/delete` — jak wyżej + `auth.logout_user(request)`.
   - `auth.current_user` (`app/auth.py`) i `login_submit`
     (`app/routers/auth.py`) odrzucają konto
     z `deleted_at` (401 / komunikat „konto zostało skasowane").
4. **UI.** Karta „Twoje dane" w `app/templates/settings.html` (przed kartą
   „Kontakt") i w zakładce Ustawienia `app/templates/mobile.html` (sekcja
   „Konto"): dwa przyciski w kolorze `danger` — „Usuń historię (posiłki, ciężar,
   aktywności)" i „Usuń konto i wszystkie dane". Każdy otwiera potwierdzenie
   z polem hasła i polem, w które trzeba wpisać `USUWAM`. Pod przyciskami zdanie
   bez upiększeń: „Dane znikają z aplikacji natychmiast. Przez 3 dni (historia)
   / 7 dni (konto) administrator może je odtworzyć na Twoją prośbę — potem są
   kasowane bezpowrotnie." Obok link do eksportu (`/api/transfer/export`) —
   „pobierz swoje dane, zanim je skasujesz".
5. **Skrypty i timer.** `scripts/purge_deleted.py` (woła `purge_due`, loguje co
   skasował) + `deploy/fit-krasnal-purge.service` i `.timer` (codziennie 03:00,
   `OnCalendar=*-*-* 03:00:00`, `Persistent=true`), instalowane w
   `deploy/setup-vm.sh` i opisane w `deploy/README.md`.
   `scripts/restore_deleted.py <email|user_id>` — znajduje kopię, tworzy konto,
   jeśli trzeba, i wczytuje przez `transfer.import_payload`.
6. **Testy `tests/test_erasure.py`** (wzorzec `clients` z
   `tests/test_saved_meals_api.py`): pełny cykl — posiłki i wagi → `wipe-data`
   → `/api/day` bez posiłków, plik kopii istnieje → `restore` przez
   `import_payload` wraca do stanu sprzed; `delete` → logowanie odbite,
   e-mail wolny (rejestracja tym samym adresem przechodzi); złe hasło → 403,
   nic nie skasowane; brak `confirm` → 422; kasowanie usera A nie tyka danych
   usera B; `purge_due` po `purge_after` kasuje plik i wiersz `user`, przed
   terminem nie rusza nic.

Weryfikacja: pełny pytest zielony → commit + push. Po deployu właściciel
sprawdza, że timer jest aktywny (`systemctl list-timers | grep purge`).
