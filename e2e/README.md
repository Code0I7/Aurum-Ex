# E2E tests

Playwright driving a real browser against a real, fully isolated Aurum
stack — not the self-hosted instance you actually use day to day. These
tests create and read real data over the real HTTP API and real rendered
UI, which is the only way to actually catch things like a CSS layout
overflow or a filter that's silently ignored — a backend-only test suite
can't see either.

Eight tests, about 25 seconds once the stack is up.

## When to run them

Not on every change. The 643 backend tests and 114 frontend ones answer
"do the numbers come out right"; these answer "does the page work", and
only a handful of screens are covered. Reach for them when a change touches
layout, navigation between pages, or UI state that has to survive a reload —
the class of thing no amount of unit testing can see — and before a release.

## Isolation

`run.sh` brings up a *second*, throwaway stack alongside your real one:

| | real instance | e2e stack |
|---|---|---|
| compose project | `aurum` (default) | `aurum-e2e` |
| Postgres database | `aurum` | `aurum_e2e` |
| web port | whatever `.env` says | 3100 |

Different project name means different containers, network, and — crucially
— a different named Postgres volume, so the e2e Postgres data directory is
physically separate from `aurum_pgdata`. `run.sh` always tears the e2e stack
down with `docker compose down -v` on exit (even on failure/Ctrl-C), so no
test data is left behind and your real instance is never touched, restarted,
or read from.

**On a published instance it needs more than a different port.** `run.sh`
overrides three values from your `.env`, and each one otherwise breaks the
run in its own way:

- `COMPOSE_PROFILES=` — empty, or a second `edge` comes up and collides with
  the real one on its TLS port;
- `AURUM_SECURE_COOKIES=false` — the stack answers over plain http, and a
  Secure cookie never reaches the browser: the login "succeeds" and the next
  page shows the login form again;
- `AURUM_ADMIN_PASSWORD` — set to a fixed throwaway value so the backend
  seeds the account at boot. Otherwise the install sits in first-run setup
  and the run depends on who gets there first.

## Running

```bash
./e2e/run.sh
```

Pass extra Playwright CLI args through, e.g. to run one file or open the
trace viewer on failure:

```bash
./e2e/run.sh tests/year-switcher.spec.ts
./e2e/run.sh --headed
```

Playwright itself runs **in a container** (the official image, which already
carries the matching browsers), so the only thing the host needs is Docker —
same as the rest of the project. `node_modules` live in a named volume
instead of being reinstalled every time.

## Signing in

The app has a login, so both the browser and the `request` fixture need a
session. `global-setup.ts` signs in once per run and saves the cookie to
`.auth/state.json`; `playwright.config.ts` hands that file to both. Doing it
per test would mean sixty logins testing the login instead of the thing the
test is about.

It signs **in** rather than running first-run setup: the account already
exists, seeded from `AURUM_ADMIN_PASSWORD` when the container booted, and
`POST /auth/setup` would answer `409` the second time around.

## Adding a test

- Seed data via the `request` fixture and the helpers in `tests/helpers.ts`
  (hits `/api/...` directly — fast and doesn't depend on clicking through a
  form). Then drive the actual page for the behavior under test.
- Tests run with `workers: 1` against one shared backend/DB within a single
  `run.sh` invocation, so give each spec's seeded data a distinct year/month
  (or otherwise non-overlapping scope) rather than relying on a clean slate
  between spec files.
- **Don't assert on a colour code or any other value the design owns.** The
  theme test used to compare `--surface-0` against `#0d0d0d` and broke the
  day the dark canvas was retuned — it was checking the palette while
  meaning to check that an explicit choice overrides the OS. It now reads
  `data-scheme` and compares surfaces against each other.
- **Put a shared click sequence in `helpers.ts`.** Five specs picked a year
  and a month on the dashboard inline, and all five broke at once when the
  default period became the year: month buttons only exist in month mode.
  `openDashboardMonth` is that sequence in one place.
