<!-- Plan prepared 2026-10-09. When done: DONE.md entry + archive/, delete this file and its TODO.md item. -->
# Merge the bobert-bag-bounty fork (Android shell, Google login, Vertex, hardening)

Fork: https://github.com/bobert-bag-bounty/bilans-kcal, **pinned to commit
`5005879`** (fork version 27.0.0). Do not merge anything newer without asking
the owner. The fork already contains all of our `main` up to `95045fe` (26.2.5),
so the merge is a pure fast-forward with no conflicts. The work is in the
follow-up fixes, not in the merge itself.

What the fork brings (all reviewed 2026-10-09, 288 tests green):
- `android-app/`: Capacitor 8 shell that loads the production site in a WebView,
  plus a native bridge in `mobile.html` (camera/gallery, haptics, Health Connect steps).
- `app/routers/oidc.py`: Google login behind `FIT_KRASNAL_AUTH` (default `password` = unchanged).
- `meal_vision`: `vertex` backend behind `FIT_KRASNAL_VERTEX_PROJECT` (unset = unchanged).
- `app/middleware.py`: CSP, origin-based CSRF, Host filter, 8 MB body limit.
  **This is active in production immediately, no flag.**
- `deploy/terraform/`, a reworked `deploy/setup-vm.sh`, `ARCHITEKTURA.md`.

## Owner decisions (made 2026-10-09, do not re-ask)

1. **Privacy note:** `PRIVACY_VERSION` = **the date the owner deploys**
   (ask the owner for the date in step 7). `CONSENT_DEADLINE = 2026-12-31`.
2. **Fork infra:** keep the code (Terraform, scripts, docs) and delete
   `plans/publikacja-i-przekazanie.md`. Its open decisions go to `TODECIDE.md`.

## Rules for the executor (from CLAUDE.md, repeated because they bite here)

- Work on branch `merge/bobert-fork`. **Never push, never touch `main`.**
  A push to `main` = deploy to the testers.
- One commit per step below. Every commit that changes `app/` bumps `VERSION`
  (Z for fixes, Y for step 3), following `VERSIONING.md`.
- Run tests for the changed files freely. Run the full `pytest` **only after
  the owner says yes** (step 8).
- Write everything in the repo (code, comments, .md, commits) in **English**.
  Existing Polish text you touch may stay Polish if you are only moving it.
- End commit messages with: `Co-Authored-By: Claude <noreply@anthropic.com>`
  (the fork author's commits keep their own authorship; do not rewrite them).

## What to read (and what not to)

| File | Lines | Why |
|---|---|---|
| `app/middleware.py` | 18–23 | the `CSP` string (step 2) |
| `tests/test_hardening.py` | 1–60 | test pattern for headers (step 2) |
| `app/routers/settings.py` | 160–195, 270–292 | Strava connect redirect; `/api/settings` consent fields |
| `app/services/consent.py` | whole file (~60) | `has_consent` / `current` (step 3) |
| `app/deps.py` | 24–30 | `require_llm_consent` gate |
| `app/services/meal_queue.py` | 115–125 | queue consent check |
| `app/config.py` | 128–136 | `PRIVACY_VERSION`, `CONSENT_DEADLINE` |
| `app/templates/mobile.html` | 146, 460–470, 1575–1605 | consent banner + `applyConsentUi` |
| `app/templates/settings.html` | 190–215 | desktop consent block (minimal change only) |
| `tests/test_consent.py` | 1–60, 120–135 | fixtures + the "older version = no consent" test |
| `app/services/usage.py` | 30–60 | `EVENTS` set |
| `CLAUDE.md`, `README.md` | grep `Fork\|fork` | lines that call this repo "the fork" |

**Do not read:** `android-app/android/**` (generated Gradle project, binaries),
`android-app/package-lock.json`, `deploy/terraform/*` (not touched by this plan),
`archive/*` whole (use `awk` per DONE.md), `ARCHITEKTURA.md` whole (only grep it
in step 5).

## Steps

### 1. Merge (no code changes)

```bash
cd ~/git/vibowanie/bilans-kcal
git status            # must be clean, on main, equal to origin/main
git remote add bobert https://github.com/bobert-bag-bounty/bilans-kcal.git
git fetch bobert
git switch -c merge/bobert-fork main
git merge --no-ff 5005879 -m "Merge bobert-bag-bounty fork (27.0.0): Android shell, Google login, Vertex, hardening"
pytest -q tests/test_hardening.py tests/test_oidc.py tests/test_meal_vision.py tests/test_consent.py
```
If `git merge` reports any conflict, stop and tell the owner (none are expected).

### 2. CSP blocks the Strava connection (bug, Z bump)

`POST /settings/strava/connect` answers with a 302 to `https://www.strava.com/oauth/authorize`.
Browsers check CSP `form-action` on redirects that follow a form submission,
and the fork's CSP allows only `'self' https://accounts.google.com`. So
"Connect Strava" in production would silently fail with a console error.
- Add `https://www.strava.com` to `form-action` in `app/middleware.py`.
- Test in `tests/test_hardening.py`: `"https://www.strava.com" in CSP`, plus a
  short comment saying why (form POST → 302 off-site).
- Grep for other off-site redirects behind a form POST:
  `grep -n "RedirectResponse(f\?\"https" -r app/routers`. Add any you find the same way.

### 3. Privacy version + grace period (Y bump)

**The trap:** `CONSENT_DEADLINE` only changes the banner text. The gate
(`deps.require_llm_consent`, `meal_queue`) uses `has_consent`, which accepts
only the **current** version. Without a grace period, bumping the version
blocks photo estimates for every tester the moment the deploy lands, even with
the deadline set to 31.12.

Implement:
- `config.py`: `PRIVACY_VERSION` default = placeholder `"2026-10-XX"` for now
  (the final date is set in step 7); `CONSENT_DEADLINE = date(2026, 12, 31)`.
  Update the comment ("deadline = until when an older-version consent still counts").
- `consent.py`: new `effective(db, user_id, kind, today) -> Consent | None` =
  `current(...)`, or, if `today <= CONSENT_DEADLINE`, the newest non-withdrawn
  consent of **any** version. `has_consent` uses `effective`. Keep `current`
  as is (it still means "consent to the current note").
  `today` = `clock.user_today(profile)` where a profile is available, otherwise
  `date.today()` (accepted: the deadline is a whole day, the edge case is harmless).
- `/api/settings` (`settings.py` ~286): `consent_llm_photos` = effective consent
  (so the Add-tab fields stay visible), new field `consent_reconfirm` = effective
  and not current.
- `mobile.html` `applyConsentUi`: show the banner when `!granted` (as today)
  **or** when `consent_reconfirm` is set. In that second case use the existing
  "Doprecyzowaliśmy… zdecyduj do DD.MM.RRRR" text. Keep the fields visible.
  The Settings → Privacy status shows "udzielona (poprzednia wersja noty) —
  potwierdź" and the button grants the current version.
- `settings.html` (desktop): no logic change. It already shows "brak" + "Włącz zgodę"
  for the current version, which is acceptable. Do not invest more here
  (mobile-first rule).
- Tests (`tests/test_consent.py`): adapt
  `test_consent_in_older_privacy_version_counts_as_no_consent` so it runs with
  the deadline in the past (monkeypatch `CONSENT_DEADLINE`). Add:
  (a) an older-version consent before the deadline → 200 on meal text + `consent_reconfirm: true`;
  (b) a withdrawn older consent → 409 even before the deadline;
  (c) granting again → `consent_reconfirm: false`.
- `privacy.html`: the fork's new paragraphs are already conditional in wording
  ("only if the operator enabled it"). Leave them. The DONE entry must state
  the note changed (Google login, Vertex AI) and that older consents count
  until 2026-12-31.

### 4. Statistics (part of done, CLAUDE.md)

- Check that the fork's events (`native_app_open`, `photo_native_camera`,
  `photo_native_gallery`, `steps_health_connect`, `login_google`) appear in
  `/usage` "top events" after a local `track()` call. They are in `EVENTS`,
  so this should work without code changes; just verify it.
- New event `photo_too_large`: in `mobile.html` `estimate()`, when the upload
  response is 413, call `track("photo_too_large")`. Add it to `EVENTS`
  (+ `tests/test_usage.py` if it lists events). Reason: the limit drops from
  15 to 8 MB, and when downscaling fails the client sends the original.
  This counter tells us whether 8 MB hurts real phones. Z bump.
- Re-consent adoption: `/admin/consents` already lists consents per user.
  Make sure it shows the **version** of each consent (add the column if it is
  missing). That is how the owner watches who has re-confirmed before 31.12.

### 5. Docs: this repo is no longer "the fork"

- `CLAUDE.md` (~line 31, 42, 53) and `README.md` (~19–30): replace the
  "Fork (this repo) adds…" wording with a neutral description: the features
  exist, they sit behind env flags, and production runs with defaults
  (`password` auth, no Vertex). Keep the one-line thanks to the fork author in README.
- `CLAUDE.md` "Stan bieżący": add one bullet saying `app/middleware.py`
  (CSP/CSRF/Host/body limit) is active in production, and adding an external
  host (script, form target, OAuth redirect) means updating `CSP`.
- `git rm plans/publikacja-i-przekazanie.md`. Copy its open decisions into
  `TODECIDE.md` as **one** new section "Fork leftovers (from 2026-10-09)":
  Flutter vs Capacitor; package name `cc.krasnal.fit` (used in the PoC APK);
  Health Connect weight (implement or remove the `READ_WEIGHT` promise from
  manifest + `android-app/README.md`); whether to move production to the
  Terraform setup; Google login in WebView vs Chrome Custom Tabs.
  Questions only, with the fork's recommendation next to each. No answers.
- `TODO.md`: the "Aplikacja mobilna (Etap 2) — Flutter" and "Nazwa pakietu"
  items: add one line each pointing to `android-app/README.md` and the new
  TODECIDE section. Do not decide anything.

### 6. Local manual check (mobile viewport)

Start the dev server (launch config `fit-krasnal`, port 8321, `FIT_KRASNAL_DEBUG=1`)
and in a 375 px viewport go through: login, Today, Add (text estimate, photo
pick), Activities, Trends, Settings, `/prywatnosc`, `/usage`. **The browser
console must have zero CSP violations.** Then restart with
`FIT_KRASNAL_STRAVA_CLIENT_ID=x FIT_KRASNAL_STRAVA_CLIENT_SECRET=y` and click
"Połącz ze Stravą" in `/settings`: the browser must navigate to strava.com
(an error page from Strava is fine; a CSP error is not). Report what you saw
and attach a screenshot.

### 7. Final privacy date

Ask the owner: "Which day will you push?" Set `PRIVACY_VERSION` to that date
(`YYYY-MM-DD`) in `config.py`, then commit. If the push slips to another day,
the owner changes this one line before pushing.

### 8. Full test suite (ask first)

Ask the owner for permission, then run `pytest -q`. Report the pass/fail count.
If anything is red, stop and report. Do not "fix" tests you did not change.

### 9. Close out (bookkeeping)

- Delete this item from `TODO.md` and delete this file.
- `DONE.md`: one line at the top of the right list. `archive/`: title + max 5
  bullets (what merged, CSP/Strava fix, grace period until 2026-12-31,
  privacy note change, new stats).
- Commit. Stop. Hand over to the owner with the checklist below.

## Owner checklist (not for the executor)

Before pushing:
- `git switch main && git merge --ff-only merge/bobert-fork`, then push at a
  time when you can watch it. Actions deploys automatically.
- No env changes are needed on the VM. Leave `FIT_KRASNAL_ALLOWED_HOSTS`
  unset at first (`*`). If you set it later, include `127.0.0.1` for the
  `deploy.sh` health check. `deploy.sh` installs the new deps (`authlib`, `httpx`).
- The new `deploy/fit-krasnal.service` (`ExecStartPre` metadata fetch) is not
  installed by `deploy.sh`. Leave it that way on `krasnal-first1`.

After the deploy:
- `/prywatnosc` shows the new version. On your phone the Add tab still works
  and the banner says "zdecyduj do 31.12.2026".
- "Connect Strava" opens Strava. A photo estimate works end to end.
- After a week, check `/usage` for `photo_too_large` and `/admin/consents` for
  how many testers have re-confirmed.
