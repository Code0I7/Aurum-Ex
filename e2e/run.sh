#!/usr/bin/env bash
# Spins up a throwaway Aurum stack for E2E tests, runs Playwright against it,
# then always tears the stack down again — including its Postgres volume.
#
# Fully isolated from the real self-hosted instance:
#   - separate compose project name (aurum-e2e)      -> separate containers/network
#   - separate Postgres database name (aurum_e2e)     -> separate data, same server
#   - separate host port (3100, vs the real one's 3000) -> no port clash
#   - `down -v` on exit removes the isolated volume, so no test data persists
#     and the real `aurum`/`aurum_pgdata` are never opened.
set -euo pipefail
cd "$(dirname "$0")/.."

export AURUM_POSTGRES_DB=aurum_e2e
export AURUM_POSTGRES_PASSWORD=aurum-e2e-only
export AURUM_WEB_PORT=3100

# Дальше — три значения, которые приходится перебивать именно потому, что
# compose читает .env настоящей установки. На локальной машине разработчика
# они совпадают с нужными; на опубликованном экземпляре — нет, и каждое
# ломает прогон по-своему.

# Без профиля: с COMPOSE_PROFILES=public поднялся бы второй edge и занял бы
# тот же TLS-порт, что настоящий. Стенду он не нужен — тесты ходят по http.
export COMPOSE_PROFILES=

# Кука сессии без флага Secure: стенд отвечает по http://localhost, и
# браузер такую куку просто не сохранит — вход «пройдёт», а следующая
# страница снова покажет форму входа.
export AURUM_SECURE_COOKIES=false

# Учётную запись стенда создаёт само приложение при старте. Так вход
# становится предсказуемым: иначе установка остаётся в режиме первичной
# настройки, и прогон зависит от того, кто успел первым.
export AURUM_ADMIN_USERNAME=admin
export AURUM_ADMIN_PASSWORD=e2e-only-password

COMPOSE="docker compose -p aurum-e2e"

cleanup() {
  $COMPOSE down -v
}
trap cleanup EXIT

$COMPOSE up -d --build

echo "waiting for http://localhost:${AURUM_WEB_PORT}/api/health ..."
# /api/health, not just / — nginx (the `web` container) answers the bare root
# well before the backend has finished running migrations + seeding, and a
# request racing ahead of that gets nginx's own HTML error page back instead
# of JSON, which the first test to touch the API then fails to parse.
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${AURUM_WEB_PORT}/api/health" >/dev/null; then
    echo "stack is up"
    break
  fi
  sleep 1
done

# Playwright запускается в контейнере, а не на машине.
#
# Иначе прогон требовал бы Node и браузер на хосте — при том что всё
# остальное в проекте поднимается одним Docker, и README это обещает.
# Официальный образ Playwright уже содержит браузеры нужной версии, так что
# ни установки, ни скачивания сотен мегабайт при каждом запуске нет.
#
# --network host нужен, чтобы из контейнера был виден localhost:3100, на
# котором отвечает стенд. node_modules лежат в томе: переустанавливать их на
# каждый прогон незачем.
PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright:v1.62.1-noble"

docker run --rm --network host \
  -v "$PWD/e2e:/e2e" \
  -v aurum_e2e_node_modules:/e2e/node_modules \
  -w /e2e \
  -e "AURUM_E2E_BASE_URL=http://localhost:${AURUM_WEB_PORT}" \
  -e "AURUM_E2E_USERNAME=${AURUM_ADMIN_USERNAME}" \
  -e "AURUM_E2E_PASSWORD=${AURUM_ADMIN_PASSWORD}" \
  -e CI=1 \
  "$PLAYWRIGHT_IMAGE" \
  sh -c 'npm install --no-audit --no-fund >/dev/null && exec npx playwright test "$@"' -- "$@"
