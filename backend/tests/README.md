# Backend tests

Real integration tests against a real Postgres database — a dedicated
`aurum_test` database created fresh, migrated, and dropped again on every
run. They never touch the real `aurum` database or its data: the app's
`lifespan` startup (which seeds against the real DB) is never triggered, and
every route's DB dependency is overridden to point at `aurum_test` instead.

The harness also pins `AURUM_SECURE_COOKIES=false` for the run (see the top
of `conftest.py`). A published instance sets it to `true` in `.env`, and
rightly so — but the test client speaks plain `http://test`, a Secure cookie
never reaches it, and the whole suite would fail over a setting no test is
about.

## Layout

Tests sit in six folders, one per question the app answers. Run one folder to
work on one area — each takes under half a minute:

| Folder | What it covers |
|---|---|
| `money/` | What happens to money: transactions, their order within a day, transfers, a transaction's own currency |
| `debts/` | Who owes whom: settlements with people, money in transit, credit terms and the pay-off calculator |
| `capital/` | What is owned: capital, assets and their valuations, investments, crypto, exchange rates |
| `plans/` | What is intended: plans, budgets, goals, recurring templates, hours worked |
| `analysis/` | What follows from it: dashboard, cash flow, reports, categories, products, advice and alerts |
| `platform/` | The app itself: login, settings, backup, spreadsheet import, directories, and rules every schema must satisfy |

`conftest.py` and `helpers.py` stay at the root — they apply to every folder.
Shared builders belong in `helpers.py` rather than in a test module: one test
file importing another is a dependency between tests, and it broke the moment
the files moved.

## Running

The stack must already be up (`docker compose up -d`). Test dependencies
aren't baked into the production image, so install them once per container
lifetime, then run pytest inside the running `backend` container — it's the
only place with network access to Postgres:

```bash
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend pytest -q
docker compose exec backend pytest -q tests/capital   # one area
```

The whole suite is about two minutes. It used to be six, and the difference
was almost entirely fixture setup rather than the tests themselves:

- the test password is hashed **once per run**. scrypt costs ~79 ms by design,
  and `client` was paying it before nearly every test by going through the real
  first-run setup. The account and session row are now written directly; the
  genuine setup and login paths are still exercised, in `platform/test_auth.py`
  and `platform/test_first_run_setup.py`;
- one event loop and **one engine** for the whole run (see `pytest.ini`). It
  used to be one engine per test, for a real reason — an asyncpg connection
  belongs to the loop that opened it — which a shared loop removes.

Re-run just `pytest -v` for subsequent runs; the `pip install` only needs
repeating after a container restart/rebuild.

**One run at a time.** The database name is fixed, so a second run drops and
recreates `aurum_test` from under the first — hundreds of unrelated failures
that look like a broken branch.

## Adding a test

- Use the `client` fixture (an `httpx.AsyncClient` wired to the app) to hit
  the API the same way the frontend does — prefer this over reaching into
  services/models directly, so tests keep verifying the actual contract.
- `account_id` and `categories` fixtures give you the same default
  account/categories a real fresh install seeds.
- Every table is truncated and reseeded before each test (see
  `conftest.py::_clean_database`), so tests don't need to worry about
  leftover state or guess at IDs from a previous test.
