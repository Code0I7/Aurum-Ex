# E2E tests

Playwright driving a real browser against a real, fully isolated Aurum
stack — not the self-hosted instance you actually use day to day. These
tests create and read real data over the real HTTP API and real rendered
UI, which is the only way to actually catch things like a CSS layout
overflow or a filter that's silently ignored — a backend-only test suite
can't see either.

## Isolation

`run.sh` brings up a *second*, throwaway stack alongside your real one:

| | real instance | e2e stack |
|---|---|---|
| compose project | `aurum` (default) | `aurum-e2e` |
| Postgres database | `aurum` | `aurum_e2e` |
| web port | 3000 | 3100 |

Different project name means different containers, network, and — crucially
— a different named Postgres volume, so the e2e Postgres data directory is
physically separate from `aurum_pgdata`. `run.sh` always tears the e2e stack
down with `docker compose down -v` on exit (even on failure/Ctrl-C), so no
test data is left behind and your real instance is never touched, restarted,
or read from.

## Status: these specs predate the login

They were written before Aurum-Ex had a login of its own, and **they do not
pass today**. Neither `helpers.ts` nor the Playwright config performs first-run
setup or signs in, so on a fresh stack `request.get("/api/accounts")` gets a
`428` ("set a password first") and the browser lands on the login screen.

Bringing them back needs one step before the run: `POST /auth/setup` in a
`globalSetup`, and a saved session (`storageState`) handed to both the browser
and the `request` fixture. Until that exists, the command below will raise the
stack and then fail honestly on the first API call. The rest of this file is
still accurate, which is why it stays.

## Running

```bash
cd e2e
./run.sh
```

Pass extra Playwright CLI args through, e.g. to run one file or open the
trace viewer on failure:

```bash
./run.sh tests/year-switcher.spec.ts
./run.sh --headed
```

## Adding a test

- Seed data via the `request` fixture and the helpers in `tests/helpers.ts`
  (hits `/api/...` directly — fast and doesn't depend on clicking through a
  form). Then drive the actual page for the behavior under test.
- Tests run with `workers: 1` against one shared backend/DB within a single
  `run.sh` invocation, so give each spec's seeded data a distinct year/month
  (or otherwise non-overlapping scope) rather than relying on a clean slate
  between spec files.
