# TODO — do zrobienia po pilocie

Notatnik na luźne punkty, których nie robię teraz, ale nie chcę ich zgubić.
Każdy punkt jest przyszłym samodzielnym zadaniem — nie planem wdrożenia.

## Kasowanie konta z 7-dniowym oknem odzyskania

Użytkownik kasuje konto. W bazie flagi `deleted_at` + soft-delete relacji,
konto znika z widoku. Przez 7 dni skrypt na VM potrafi je przywrócić —
warunek: nowe konto zarejestrowane na ten sam e-mail (świadoma podatność
zaakceptowana na pilota). Po założeniu nowego konta tester **nie widzi**
starych danych — musi być przekonany, że są nie do odzyskania. Twarda
kasacja po 7 dniach.

## Kasowanie danych z konta (czyszczenie historii)

Analogicznie: użytkownik z poziomu ustawień czyści posiłki/wagi/kolejkę.
Widocznie znikają natychmiast. Twarda kasacja finalizuje się po **3 dniach**.
Do tego czasu skrypt na VM potrafi przywrócić. Użytkownik ma być
przekonany, że skasował, tak samo jak w punkcie wyżej.

## Statystyki użycia — widok administratora

Nowa zakładka `/usage` (albo `/admin`) widoczna wyłącznie dla użytkownika
`krasnal@krasnal.cc` (twardo w kodzie, bez roli w bazie). Pokazuje agregaty
per `user_id` (bez e-maili, bez surowych danych osobowych): liczba
posiłków/dzień, liczba synców Garmina, liczba szacowań LLM, ostatnia
aktywność, wielkość bazy per user. Do orientacji, ilu testerów faktycznie
używa i jak intensywnie.
