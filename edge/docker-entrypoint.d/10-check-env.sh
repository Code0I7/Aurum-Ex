#!/bin/sh
# Проверка до подстановки. Запускается раньше штатного
# 20-envsubst-on-templates.sh (порядок лексический), потому что envsubst
# молча заменяет незаданную переменную пустой строкой: без этой проверки
# пустой ключ калитки превратил бы её в «пускать всех, у кого нет куки»,
# и заметить это можно было бы только случайно.
set -eu

fail() {
  echo "[aurum-edge] $1" >&2
  exit 1
}

[ -n "${AURUM_DOMAIN:-}" ] || fail "AURUM_DOMAIN не задан — nginx не знает, какое имя обслуживать."
[ -n "${AURUM_GATE_KEY:-}" ] || fail "AURUM_GATE_KEY не задан — калитка была бы открыта настежь."

# Короткий ключ перебирается, и калитка перестаёт быть калиткой.
if [ "$(printf %s "$AURUM_GATE_KEY" | wc -c)" -lt 16 ]; then
  fail "AURUM_GATE_KEY короче 16 символов. Сгенерировать: openssl rand -hex 16"
fi

CERT="/etc/letsencrypt/live/${AURUM_DOMAIN}/fullchain.pem"
[ -r "$CERT" ] || fail "Не читается сертификат $CERT — выпустите его до запуска."

echo "[aurum-edge] Домен ${AURUM_DOMAIN}, калитка включена."
