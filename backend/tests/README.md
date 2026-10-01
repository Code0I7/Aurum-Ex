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

## Running

The stack must already be up (`docker compose up -d`). Test dependencies
aren't baked into the production image, so install them once per container
lifetime, then run pytest inside the running `backend` container — it's the
only place with network access to Postgres:

```bash
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend pytest -v
```

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
