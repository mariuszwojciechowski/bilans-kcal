# TODO — do zrobienia po pilocie

Notatnik na luźne punkty, których nie robię teraz, ale nie chcę ich zgubić.
Każdy punkt jest przyszłym samodzielnym zadaniem — nie planem wdrożenia.

Przy każdym punkcie **szacowanie złożoności w skali 1-10**:

- **1** — wpisanie tej linijki tutaj zajmuje tyle samo co samo zrobienie.
- **3** — kilka godzin roboty, znane rozwiązanie.
- **5** — wieczór do dnia pracy, jakieś decyzje po drodze.
- **7** — kilka dni, sensowny plan przed startem.
- **10** — tygodnie, wymaga zewnętrznych rzeczy (usługa mailowa, nowa infrastruktura).

---

## GitHub Pages — czerwony pipeline po skasowaniu docs/ (1/10)

Po usunięciu katalogu `docs/` (commit `091844d`) workflow *pages build and
deployment* w GitHub Actions faluje: repo miało w Settings → Pages → Source
ustawione na `docs/` folder, którego już nie ma. Stary content nadal
serwuje się z ostatniego udanego deploya, ale każdy push wywala nowego
builda. Do wyboru: (a) wyłączyć Pages w Settings → *None* (przerywa też
serwowanie starej wersji), (b) zostawić w Source folder `/` i wrzucić
minimalny `index.html` który redirectuje na `fit.krasnal.cc` (zabija starą
wersję po naszej stronie), (c) ignorować pipeline — nic to nie psuje,
tylko brzydko wygląda w Actions.

## Landing page — drobne poprawki (1/10)

- Do karty *Fit Krasnal* dopisać informację o wygodniejszym widoku dla
  telefonu: `fit.krasnal.cc/mobile`.
- Adresy stron (`fit.krasnal.cc`, `mariuszwojciechowski.github.io/bilans-kcal`,
  `pikimocy.krasnal.cc`) zamienić na klikalne linki — teraz są tylko tekstem.

## Skrypt na serwerze do resetu hasła (1/10)

Analogiczny do `scripts/adopt_local_user.py`, tyle że dla dowolnego użytkownika:
`scripts/reset_password.py <email>` — pyta o nowe hasło w terminalu (żeby nie
lądowało w historii bash), haszuje i zapisuje w bazie. Do użycia, gdy tester
zapomni hasła i napisze do Ciebie.

## Edytowanie liczby kroków w wersji desktopowej (1/10)

Dashboard desktopowy wyświetla kroki z Garmina, ale nie ma pola do ręcznego
wpisania — jest tylko w `/mobile`. Dodać input liczbowy obok statystyki kroków
(analogicznie do `saveDaySteps()` w `mobile.html`) z `POST /api/day/{day}/steps`.
Przydatne gdy krok Garmina nie zsynchronizował się albo użytkownik nie ma
zegarka.

## Zmiana hasła z poziomu Ustawień (2/10)

Dodatkowa karta w `/settings`: pola *stare hasło*, *nowe hasło*, *powtórz*.
Endpoint `POST /settings/password` używa `auth.verify_password` na starym,
`auth.hash_password` na nowym, sprawdza kryteria minimalnej długości. Ten
sam wzorzec błędów co formularze rejestracji.

## ~~Zmniejszanie zdjęcia w przeglądarce przed wysłaniem na serwer~~ ✓ zrobione (commit b30b1eb)

## Redirect po zalogowaniu w zależności od urządzenia (2/10)

Dziś każdy po `/login` ląduje na dashboardzie desktopowym. Prosta heurystyka
po `User-Agent`: telefon → `/mobile`, komputer → `/`. Sam tester może to
i tak przełączyć w każdej chwili — chodzi o pierwsze wrażenie.

## Widok Ustawienia w wersji mobilnej (3/10)

Obecny `/mobile` w zakładce *Ustawienia* linkuje do desktopowego `/settings`,
który jest ciasny na małym ekranie. Zrobić natywną wersję: formularz profilu
(płeć, data ur., wzrost, ciężar), styl życia, cel, klucz Gemini, przycisk
połączenia z Garminem. Wszystko przez fetch do istniejących endpointów.

## Widok Trendy w wersji mobilnej (3/10)

`/mobile` nie ma trendów — testerzy chcący zobaczyć postęp wagi/bilansu muszą
przełączać się na `/trends` (widok desktopowy). Dodać czwartą zakładkę
z wykresami — te same, które są w desktopowej Trendy, mniejsze i bez tabel.
Wykresy już generuje `app/services/charts.py`, można je serwować przez nowy
endpoint JSON i rysować po stronie klienta, albo po prostu wstawić SVG z
serwera pod URL-em typu `/trends/embedded?days=30`.

## ~~Ręczne dodawanie posiłku (bez szacowania)~~ ✓ zrobione (commit b30b1eb + 2485da5)

## Ręczny wpis aktywności fizycznej (bez Garmina) (4/10)

Dla testerów bez zegarka sportowego: formularz do wpisania czasu trwania
i rodzaju aktywności, który przelicza go na spalone kcal metodą MET
(Metabolic Equivalent of Task — standardowe tabele ACSM). Pola:
aktywność (lista: rower, pływanie, bieganie, ćwiczenia siłowe, marsz szybki),
czas [minuty], opcjonalnie intensywność (lekka/umiarkowana/intensywna —
różne wartości MET). Wzór: `kcal = MET × masa_ciała_kg × czas_h`.
Masa ciała z ostatniego pomiaru w bazie. Zapis do `Activity` (tabela już
istnieje, `app/models.py`) z `source="manual"` — to samo co Garmin, więc
bilans i TDEE od razu uwzględniają aktywność. Wyświetlać w dashboardzie
i `/mobile` w sekcji bilansu obok kroków. Nie zastępuje synchronizacji
Garmina — jest alternatywą dla tych, którzy go nie mają.

## ~~Dashboard lepiej wyglądający na telefonie~~ ✓ zrobione — jeden widok responsive (commit poniżej)

Widok `/` (desktopowy) na iPhonie/Androidzie: tabele posiłków rozciągają się
poza ekran, statystyki się gniotą. Dodać `@media (max-width: 640px)` który
zamienia tabele na listy kart (jedna karta = jeden posiłek), zwęża statystyki
do dwóch kolumn. Alternatywa: po prostu przekierowywać telefon na `/mobile`
(punkt "Redirect po zalogowaniu" wyżej).

## Statystyki użycia — widok dla Ciebie (4/10)

Nowa zakładka `/usage` widoczna wyłącznie dla `krasnal@krasnal.cc`
(twardo w kodzie, bez roli w bazie). Pokazuje agregaty per `user_id`
(bez e-maili, bez samych danych osobowych): liczba posiłków/dzień,
liczba synców Garmina, liczba szacowań przez Gemini, ostatnia aktywność,
wielkość bazy per user. Do orientacji, ilu testerów faktycznie używa
i jak intensywnie.

## Instalowanie na ekranie głównym telefonu (4/10)

Żeby `fit.krasnal.cc/mobile` można było "dodać do ekranu głównego" jak zwykłą
aplikację (ikona krasnala na home screen, otwiera się na pełnym ekranie bez
paska adresu). Wymaga: `manifest.webmanifest` z metadanymi i ikonami,
`sw.js` w minimalnej wersji (rejestracja + fallback cache). W poprzedniej
wersji były gotowe pliki tego typu — można wziąć z historii gita.
Uwaga: sam manifest nie da działania offline — to osobna, dużo większa robota.

## Kasowanie konta z 7-dniowym oknem odzyskania (6/10)

Użytkownik kasuje konto. W bazie flagi `deleted_at` + soft-delete relacji,
konto znika z widoku. Przez 7 dni skrypt na serwerze potrafi je przywrócić —
warunek: nowe konto zarejestrowane na ten sam e-mail (świadoma podatność
zaakceptowana na pilota). Po założeniu nowego konta tester **nie widzi**
starych danych — musi być przekonany, że są nie do odzyskania. Twarda
kasacja po 7 dniach (skrypt uruchamiany z cron / systemd timer).

## Kasowanie danych z konta — czyszczenie historii (6/10)

Analogicznie do wyżej: użytkownik z poziomu ustawień czyści posiłki/wagi/kolejkę.
Widocznie znikają natychmiast. Twarda kasacja finalizuje się po **3 dniach**.
Do tego czasu skrypt na serwerze potrafi przywrócić. Użytkownik ma być
przekonany, że skasował — tak samo jak przy kasowaniu konta.

## Prawdziwe „zapomniałem hasła" (mailem) (8/10)

Przycisk *"nie pamiętam hasła"* → formularz z e-mailem → link resetu
wysyłany na skrzynkę → tester klika, ustawia nowe hasło. Wymaga:
tabeli tokenów resetu w bazie, szablonu maila, konfiguracji wysyłki
(przez Gmail SMTP relay albo zewnętrzną usługę), ustawienia SPF/DKIM na
`krasnal.cc`, testowania że maile nie lądują w spamie. Kilka dni pracy,
w większości spoza samego kodu appki.


## Integracja z innym zrodlami w zakresie spalanych kcal (??/10)

Apple Watch, Fitbit, Whoop, Oura, Health Connect
