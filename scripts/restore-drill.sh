#!/usr/bin/env bash
# Проверка резервной копии восстановлением.
#
# Снятая копия ничего не гарантирует: убедиться, что она восстанавливается,
# можно только восстановив её. Этот скрипт поднимает чистую установку
# рядом, заливает в неё копию тем же путём, которым это делает человек в
# настройках, и сверяет числа с оригиналом.
#
# Полностью в стороне от рабочей установки, по тем же правилам, что и e2e:
#   - свой проект compose (aurum-restore)   -> свои контейнеры и сеть
#   - своя база (aurum_restore)             -> свои данные
#   - свой том                              -> aurum_pgdata не открывается
#   - свой порт (3200)                      -> не спорит с рабочим
#   - `down -v` на выходе                   -> ничего не остаётся
#
# Использование:
#   scripts/restore-drill.sh копия.json [контрольные-числа.json]
#
# Второй аргумент — вывод scripts/backup_numbers.py, снятый с рабочей
# установки. Передан — скрипт сверяет и возвращает ненулевой код при
# расхождении. Не передан — просто печатает, что получилось.
#
# Памяти нужно примерно как ещё одной установке. На сервере, где её в обрез,
# рабочую установку стоит остановить (`docker compose stop web backend edge`)
# и поднять обратно после — копия снимается до остановки.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP="${1:?укажите файл копии: scripts/restore-drill.sh копия.json [числа.json]}"
EXPECTED="${2:-}"
[ -f "$BACKUP" ] || { echo "нет такого файла: $BACKUP" >&2; exit 1; }

export AURUM_POSTGRES_DB=aurum_restore
export AURUM_POSTGRES_PASSWORD=restore-drill-only
export AURUM_WEB_PORT=3200
# Те же три перебивки, что и у e2e, и по тем же причинам: compose читает
# .env рабочей установки. Без профиля — чтобы не поднимался второй edge на
# занятом порту; без Secure — иначе кука входа не доедет по http; с паролем
# — чтобы учётная запись была сразу, а не ждала первичной настройки.
export COMPOSE_PROFILES=
export AURUM_SECURE_COOKIES=false
export AURUM_ADMIN_USERNAME=admin
export AURUM_ADMIN_PASSWORD=restore-drill-only-password

COMPOSE="docker compose -p aurum-restore"
JAR="$(mktemp)"

cleanup() {
  rm -f "$JAR"
  $COMPOSE down -v
}
trap cleanup EXIT

echo "== поднимаю чистую установку на порту ${AURUM_WEB_PORT}"
$COMPOSE up -d --build

echo "== жду, пока она ответит"
for _ in $(seq 1 90); do
  if curl -sf "http://localhost:${AURUM_WEB_PORT}/api/health" >/dev/null; then break; fi
  sleep 1
done
curl -sf "http://localhost:${AURUM_WEB_PORT}/api/health" >/dev/null || {
  echo "установка не поднялась" >&2
  exit 1
}

echo "== вхожу"
curl -sf -c "$JAR" -X POST "http://localhost:${AURUM_WEB_PORT}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"${AURUM_ADMIN_USERNAME}\", \"password\": \"${AURUM_ADMIN_PASSWORD}\"}" \
  >/dev/null

echo "== заливаю копию тем же путём, что и кнопка в настройках"
# --fail-with-body: при отказе нужно видеть причину, а не только код.
curl --fail-with-body -s -b "$JAR" -X POST \
  "http://localhost:${AURUM_WEB_PORT}/api/backup/import" \
  -H "Content-Type: application/json" \
  --data-binary "@${BACKUP}" | head -c 400
echo

echo "== считаю, что получилось"
$COMPOSE cp scripts/backup_numbers.py backend:/app/backup_numbers.py
$COMPOSE exec -T backend python /app/backup_numbers.py /tmp/after.json >/dev/null
$COMPOSE cp backend:/tmp/after.json ./restore-drill-after.json

if [ -n "$EXPECTED" ]; then
  echo "== сверяю с оригиналом"
  python3 - "$EXPECTED" ./restore-drill-after.json <<'PY'
import json
import sys

before = json.load(open(sys.argv[1], encoding="utf-8"))
after = json.load(open(sys.argv[2], encoding="utf-8"))

bad = []
for section in ("counts", "sums"):
    keys = sorted(set(before[section]) | set(after[section]))
    for key in keys:
        was, now = before[section].get(key, "нет"), after[section].get(key, "нет")
        if str(was) != str(now):
            bad.append((section, key, was, now))

total = len(before["counts"]) + len(before["sums"])
if bad:
    print("РАСХОЖДЕНИЯ (%d из %d):" % (len(bad), total))
    for section, key, was, now in bad:
        print("  %-9s %-30s было %-18s стало %s" % (section, key, was, now))
    sys.exit(1)

print("сошлось всё: %d показателей, расхождений нет" % total)
PY
else
  python3 -c "
import json
d = json.load(open('./restore-drill-after.json', encoding='utf-8'))
print('строк по таблицам:')
for k, v in sorted(d['counts'].items()):
    if v:
        print('  %-34s %6d' % (k, v))
print('суммы:')
for k, v in d['sums'].items():
    print('  %-30s %s' % (k, v))
"
fi
