# Do decyzji właściciela

Pytania, na które **nie wolno odpowiedzieć za właściciela** — blokują plan
implementacji. Sesja, która to czyta: **zadaj te pytania właścicielowi**
(pojedynczo, z rekomendacją), zapisz odpowiedzi w tym pliku, a potem rozpisz
plan w `plans/` i wpis w [TODO.md](TODO.md). Odpowiedziane pytania usuń z tego
pliku (decyzja idzie do planu, nie zostaje tutaj).

---

## Aktywności z wielu źródeł: Garmin + Strava + ręczne (otwarte od 2026-09-11)

**Skąd to się wzięło:** właściciel opisał 5 scenariuszy użycia (Garmin jako
jedyne źródło; Garmin + ręczne; tylko Strava + ręczne; Garmin na kcal/wagę
ale Strava na aktywności z licznika rowerowego; ta sama aktywność 3× —
z Garmina, ze Stravy przez Wahoo i ze Stravy przez Garmina). Wnioski z analizy
kodu, które trzeba znać, żeby zrozumieć pytania:

- Dziś cała logika wydatku stoi na jednym bicie: `a.source == "manual"`
  ([day.py:187](app/services/day.py:187)) = „dolicz na wierzch", wszystko inne
  = „już jest w dobowym pomiarze". Scenariusze 4 i 5 są tym nierozstrzygalne.
- Duplikat nie psuje tylko listy: `steps_kcal = kcal_active_garmin −
  activities_net` ([day.py:277](app/services/day.py:277)) i baza NEAT
  ([day.py:112](app/services/day.py:112)) odejmują aktywności od pomiaru, więc
  duplikat odejmuje się dwa razy i truje 7-dniową bazę prognozy doby.
- `get_provider_for_user` bierze **tylko jedno** źródło (Garmin > Strava,
  [providers/__init__.py:44](app/providers/__init__.py:44)) — w scenariuszach
  4 i 5 Stravy w ogóle nie pobieramy.
- Kasować wolno **tylko** wpisy ręczne
  ([routers/day.py:144](app/routers/day.py:144)).
- `Activity` nie ma godziny startu, tylko `date`
  ([models.py:103](app/models.py:103)) — **bez znacznika czasu żaden
  automatyczny dedup nie jest możliwy**.
- `sync_range` nie ustawia `source` ([sync.py:72](app/services/sync.py:72)),
  więc aktywności ze Stravy leżą w bazie jako `source="garmin"`.

**Proponowany kierunek (do potwierdzenia razem z pytaniami):** dwa bity per
aktywność zamiast jednego — `counts_in_totals` (czy jest już w dobowym
pomiarze) i `duplicate_of_id` (czy to duplikat), plus `started_at` (UTC),
`deleted_at` (tombstone: sync nie wskrzesza skasowanych), `sync_all_sources`
(totale i waga z jednego źródła, aktywności ze wszystkich podłączonych),
`dedup_day` po każdym imporcie i „odśwież dzień ze źródła" jako ścieżka
naprawy pomyłki.

### Pytania

1. **Czy „force refresh" (odśwież dzień ze źródła) wolno ruszać dni
   domknięte?** Przestawia kalibrację adaptacyjną i bazę NEAT, czyli zmienia
   historię i prognozy.
   *Rekomendacja: wolno, ale tylko na jawne żądanie i z ostrzeżeniem —
   nigdy automatycznie.*
2. **Która wartość kcal wygrywa w grupie duplikatów?** Garmin liczy z tętna,
   Wahoo/Strava z mocy — dla tej samej jazdy wyjdzie np. 730 vs 690.
   *Rekomendacja: zawsze źródło dobowych totali (Garmin), bo tylko ono ma
   spoczynek per aktywność (`kcal_bmr_garmin`) do policzenia kcal netto.*
3. **Duplikaty chowamy automatycznie** (oznaczone przez dedup, user je tylko
   przegląda w zwiniętej sekcji i ewentualnie kasuje), **czy pokazujemy
   wszystko płasko** i kasowanie zostawiamy użytkownikowi, jak w opisie
   scenariuszy 3-5?
   *Rekomendacja: automatyczne oznaczenie + zwinięte „N duplikatów" z
   możliwością skasowania — inaczej przy Wahoo+Garmin+Strava user kasuje
   dwa wpisy po każdym treningu.*
4. **Progi dopasowania duplikatów.** Propozycja: start ±10 min, czas trwania
   ±25%, zgodny typ. Za luźne przy interwałach rozbitych na dwa pliki, za
   ciasne przy różnych zaokrągleniach czasu między urządzeniami.
   *Rekomendacja: zacząć od ±10 min / ±25% i zmierzyć na `/usage`, ile
   duplikatów łapie automat, a ile user kasuje ręcznie.*
5. **Soft delete dla wszystkiego, czy tylko dla zsynchronizowanych?** Tombstone
   dla wpisów z Garmina/Stravy jest konieczny (inaczej sync je wskrzesza).
   Pytanie dotyczy wpisów ręcznych: czy też mają mieć „przywróć".
   *Rekomendacja: soft delete dla wszystkiego — jedna ścieżka undo, kosztem
   filtra `deleted_at` w 5 zapytaniach (day, trends, sync, usage, transfer).*

### Use case'y do potwierdzenia przy okazji (nie były na liście właściciela)

- Ręczny wpis, który **potem** dosyła zegarek (user dodaje bieg o 18:00, Garmin
  przywozi ten sam o 20:00) — duplikat manual↔sync.
- Aktywność ze Stravy **bez kalorii** (joga, siłownia bez HR i mocy): dziś nie
  wchodzi do wydatku wcale (warunek `kcal_garmin is not None`) — czy fallback
  na model MET (`energy.activity_kcal_model`)?
- Scenariusz „tylko Strava": brak kroków, brak dobowych totali i brak wagi z
  API — kalibracja pracuje na modelu, nie na pomiarze. Czy powiedzieć to
  wprost w UI?
- Odłączenie źródła / podłączenie **innego** konta Stravy — co z już
  zsynchronizowanymi aktywnościami.
- Eksport/import ([transfer.py](app/services/transfer.py)) musi przenosić
  `source`, tombstone'y i flagi duplikatów, inaczej import wskrzesza skasowane.
- Dedup musi porównywać czas w UTC, nie daty (trening 23:40 wpada u Garmina
  i Stravy w różne doby).
- Limity API przy „force": dzień = lista + `DetailedActivity` per aktywność,
  więc „force 30 dni" to setki requestów wobec 100/15 min u Stravy.
- Aktywności wielodobowe (ultra) lądują w dniu startu z absurdalnym wydatkiem
  doby — do zapisania jako znany limit.
