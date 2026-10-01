# Contributing to Aurum-Ex

Thanks for considering a contribution — code, docs, bug reports, and ideas are all welcome.

Aurum-Ex grew out of [Zproger/Aurum](https://github.com/Zproger/Aurum) and has since become a project of its own. A fix that belongs to base Aurum is better sent upstream, where it reaches everyone.

## Getting a dev environment running

The fastest path to a working environment is the same Docker Compose setup end users run:

```bash
cp .env.example .env
docker compose up -d --build
```

This gives you Postgres, the FastAPI backend (with migrations applied automatically on boot), and the built frontend served through nginx at `http://localhost:3000`.

For data to look at while you work, seed a demo install:

```bash
docker compose cp scripts/demo_seed.py backend:/app/demo_seed.py
docker compose exec backend python /app/demo_seed.py ru   # or en
```

[scripts/demo_seed.py](scripts/demo_seed.py) expects an empty database and makes up every number in it.

For active frontend development with hot reload:

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies API calls to whatever backend is running — point it at the Dockerized backend above, or run the backend locally:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Before opening a PR

- **Frontend:** `npm run build` (runs `tsc -b` then `vite build`) must pass with no type errors,
  and `npm run test` (Vitest) must be green — a few seconds. The suite covers the pure logic in
  `src/lib`: bank-statement parsing, money formatting, the plan schedule, work-hour pricing, the
  return calculator. `npm run test:watch` while you work. Components aren't covered yet; that
  would need jsdom, which is deliberately not installed until something needs it.
- **Backend:** new tables or columns need an Alembic migration (`alembic revision --autogenerate -m "..."`) — check the generated migration by hand, autogenerate isn't always right.
- **Tests:** `pytest` in `backend/` must pass (it needs a Postgres — the compose one will do).
  The runner isn't in the production image, so install it first:
  `docker compose exec backend pip install -r requirements-dev.txt`, then
  `docker compose exec backend pytest -q` (about two minutes). Tests live in six
  folders by area — `tests/money`, `tests/debts`, `tests/capital`, `tests/plans`,
  `tests/analysis`, `tests/platform` — so you can run just the one you're
  touching. See [backend/tests/README.md](backend/tests/README.md).
- **New user-facing text** goes through the translation system in `frontend/src/lib/i18n.ts` (both `ru` and `en` — the `en` object is typed against `ru`'s keys, so a missing translation is a build error, not a runtime surprise) rather than being hardcoded in a component.
- **Mobile:** check your change at a narrow viewport — Aurum-Ex is designed mobile-first.
- Keep PRs focused. A bug fix doesn't need an accompanying refactor.

## Reporting bugs

Open an [Issue](../../issues) with steps to reproduce.

## Proposing features

Open an [Issue](../../issues) first for anything that changes the data model or adds a new area of the app — it's a lot easier to align on the shape of a feature before code exists than to rework a finished PR.

## License

Aurum-Ex is licensed under [PolyForm Noncommercial 1.0.0](LICENSE) — the original's license, unchanged — not a traditional OSI open source license — see the [README's License section](README.md#license) for what that means in practice. By submitting a PR, you agree your contribution is licensed under the same terms as the rest of the project.
