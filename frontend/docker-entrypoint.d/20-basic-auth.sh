#!/bin/sh
# Runs automatically before nginx starts (official nginx image convention:
# every executable script in /docker-entrypoint.d/ is sourced on boot).
#
# Второй, необязательный слой поверх собственного входа приложения.
#
# В оригинальном Aurum входа не было вовсе, и этот скрипт был единственной
# защитой. У Aurum-Ex вход свой — страница логина, сессия в куке, задержка
# после неудачных попыток, — поэтому basic auth здесь ровно для одного:
# чтобы форма входа не показывалась постороннему, который просто нашёл
# адрес. Если AURUM_BASIC_AUTH_USER и AURUM_BASIC_AUTH_PASSWORD заданы,
# nginx требует пароль на всё (интерфейс и API), кроме проверки
# работоспособности — она должна отвечать без пароля, иначе HEALTHCHECK
# докера и внешний мониторинг сочтут контейнер мёртвым.
#
# При публикации наружу ту же работу делает калитка по секретной ссылке
# (см. edge/templates/default.conf.template): она удобнее тем, что вводить
# ничего не нужно, а закрывает то же самое.
set -eu

AUTH_FRAGMENT=/etc/nginx/basic-auth.conf

if [ -n "${AURUM_BASIC_AUTH_USER:-}" ] && [ -n "${AURUM_BASIC_AUTH_PASSWORD:-}" ]; then
  HASH="$(openssl passwd -apr1 "$AURUM_BASIC_AUTH_PASSWORD")"
  echo "${AURUM_BASIC_AUTH_USER}:${HASH}" > /etc/nginx/.htpasswd
  cat > "$AUTH_FRAGMENT" <<EOF
auth_basic "Aurum";
auth_basic_user_file /etc/nginx/.htpasswd;
EOF
  echo "[aurum] Basic auth enabled for user '${AURUM_BASIC_AUTH_USER}'."
else
  : > "$AUTH_FRAGMENT"
  echo "[aurum] Basic auth is off — the app's own login screen is the only gate." >&2
fi
