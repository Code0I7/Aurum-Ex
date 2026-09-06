<div align="center">

# Aurum-Ex

**See where every dollar comes from. Know where every dollar goes.**

**Ex — от Extended.** Aurum-Ex это расширенный форк [Aurum](https://github.com/Zproger/Aurum) от [ZProger](https://github.com/ZProger): тот же самостоятельно размещаемый учёт личных финансов, дополненный мультивалютностью, категориями произвольной вложенности, позициями в чеке, участниками и расчётами с людьми.

[![Fork of Zproger/Aurum](https://img.shields.io/badge/fork%20of-Zproger%2FAurum-6E7B74.svg)](https://github.com/Zproger/Aurum)
[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)

[Отличия](#-чем-это-отличается-от-aurum) • [Getting Started](#-getting-started) • [API Docs](DOCS.md) • [Security](#-security--self-hosting) • [License](#-license) • [Благодарности](#-благодарности)

</div>

> **Это форк, а не оригинал.** Оригинальный проект — **[Zproger/Aurum](https://github.com/Zproger/Aurum)**, автор **[ZProger](https://github.com/ZProger)**. Здесь ведётся переработанная и расширенная версия под другой сценарий использования. Оригинал развивается независимо: вопросы и баги по нему — в его репозиторий, а не сюда.
>
> `Required Notice: Copyright ZProger (https://github.com/ZProger)`

## 🧭 Чем это отличается от Aurum

Форк вырос из попытки заменить самодельную таблицу учёта — из тех, что люди годами ведут в Google Sheets. У таких таблиц набирается набор ограничений, не решаемых внутри них самих: один уровень подкатегорий, отсутствие позиций в чеке, невозможность отделить переводы от других людей от собственного заработка и стартовый остаток счёта, который приходится проводить доходом.

Направления переработки:

- **Категории произвольной вложенности** вместо одного уровня, с выбором любого уровня в транзакции.
- **Мультивалютность** с курсами ЦБ на дату операции: капитал одной суммой и с разбивкой по валютам.
- **Позиции в чеке** — необязательные, с количеством, единицей и ценой, приведённой к базовой мере.
- **Участники** — на кого пришёлся доход или расход, включая питомцев.
- **Расчёты с людьми** — переводы от других людей не считаются заработком; долги и займы различаются.
- **Справочник товаров и магазинов** — динамика цен на конкретный товар и сравнение точек продаж.
- **Настоящий вход** вместо HTTP Basic Auth.
- **Планирование** разовое, ежемесячное и подневное, на несколько лет вперёд.
- **Импорт истории из таблицы** — CSV-выгрузка листа операций с предпросмотром до записи. Формат и способ приспособить разбор под свою таблицу описаны в [docs/spreadsheet-import.md](docs/spreadsheet-import.md).

Работа идёт поэтапно. Ниже описан текущий функционал, во многом ещё унаследованный от оригинала; скриншоты пока тоже оригинальные.

## 🖼️ Screenshots

<div align="center">

<img src="images/1.png" alt="Aurum dashboard — real income, spending, savings rate, spending by category, and recent transactions" width="100%" />

<br /><br />

<img src="images/2.png" alt="Aurum net worth timeline with full asset allocation breakdown" width="100%" />

<br /><br />

<table>
<tr>
<td width="50%"><img src="images/3.png" alt="Capital grouped by type (income / neutral / drain) and by risk level" /></td>
<td width="50%"><img src="images/4.png" alt="Transactions list with filters" /></td>
</tr>
<tr>
<td width="50%"><img src="images/5.png" alt="Cash flow chart, income vs. expense by month" /></td>
<td width="50%"><img src="images/6.png" alt="Category spending report over time" /></td>
</tr>
</table>

</div>

---

## 📖 Overview

Most finance apps show you a pie chart of last month's spending and call it a day. **Aurum goes further.**

It's built for people who don't just want to **log** transactions — they want to understand the **mechanics** of their money: how capital grows or shrinks over time, which assets are pulling their weight, which subscriptions are quietly draining them, and which income streams are actually passive versus which just look that way on paper.

Aurum treats your financial life as a **system**, not a spreadsheet.

## 💡 Why Aurum

- **Fragmentation is the enemy.** Bank apps, brokerage apps, crypto wallets, spreadsheets, subscription trackers — your financial picture is scattered across a dozen tools that don't talk to each other.
- **Most trackers stop at "what happened."** Aurum also flags rising spending categories, unbudgeted expenses, and shifts in your savings rate — before they become a problem.
- **The 80/20 rule, enforced.** Aurum can group your capital by risk level and warn you the moment too much of it is exposed.
- **It should be free, forever — for you.** Financial clarity shouldn't sit behind a paywall. Aurum is source-available and self-hosted — your data never leaves your own server, and personal use is free forever. (See [License](#-license) — the code is open to read, run, and modify, but not to resell.)

## 🧩 Core Features

### 💰 Cash Flow & Transactions
Log income, expenses, and transfers across as many accounts as you want, organized into categories (with one level of subcategories) plus free-form tags, and searchable. One purchase spanning multiple subcategories of the same parent (a grocery receipt part "Sweets", part "Alcohol") can be recorded as a single split transaction instead of several — every report and chart still counts each share under its own category. Already have history elsewhere? Import a bank's CSV export in a guided 3-step wizard instead of typing every line by hand. A dedicated Cash Flow view charts income vs. expense month by month.

### 📈 Net Worth Engine
A live net worth timeline (30 days to all-time) aggregating cash and every manually tracked asset — investments, crypto, real estate, vehicles, precious metals — into one number, with a full breakdown by asset class, by how each asset behaves (income / neutral / drain), and by risk level.

### 🪙 Crypto Tracker
A CoinMarketCap-style portfolio tab for the coins you actually hold: live price plus 1h/24h/7d change, your holdings value, average buy price, and profit/loss — computed from a full buy/sell history, no separate portfolio tracker needed. Refresh on demand with one button, or let it auto-refresh once a day; either way it plugs straight into the Net Worth engine above as just another tracked asset.

### 🎯 Budgets, Goals & Recurring Payments
Set a monthly limit per category and watch progress bars fill up. Track savings goals with a running contribution log. Register recurring bills and post them with one click when they're due — nothing runs automatically in the background.

### 📊 Reports & Advice
Rank every category by total spend over any custom period to find what's actually eating your budget. A rules-based Advice tab surfaces rising spending categories, unbudgeted top expenses, and month-over-month savings rate trends in plain language.

### 🧮 Returns Calculator
A standalone ROI calculator: enter what you'd invest and what it would pay you monthly, and see the annual return, payback period, and a compound-interest projection — with a year-by-year comparison chart of compounding vs. just banking the cash — before you commit to a purchase.

### 🔔 Proactive Alerts
Aurum watches your numbers in the background and surfaces a warning the moment something crosses a threshold you configure: a sustained negative cash flow streak, a declining net worth trend, an over-budget category, too much capital sitting at risk, or cash sitting idle in an account for too long.

### 🌐 Bilingual, Mobile-First
Full Russian/English UI with a language switch in Settings, a light/dark/system theme toggle, and every screen designed mobile-first from day one.

### 💾 Full Backup & Restore
Export your entire dataset — accounts, transactions, assets, budgets, goals — to a single JSON file at any time, and restore it later on a fresh install.

## 🚀 Getting Started

Aurum ships as three containers — Postgres, a FastAPI backend, and an nginx-served frontend — wired together with Docker Compose. No local Python, Node, or Postgres installation needed; Docker is the only requirement.

### 1. Install Docker

You need **Docker Engine** and the **Docker Compose plugin** (the `docker compose` command, not the older standalone `docker-compose`).

- **macOS / Windows:** install [Docker Desktop](https://www.docker.com/products/docker-desktop/) — it bundles both.
- **Linux:** follow the [official install guide](https://docs.docker.com/engine/install/) for your distribution, then install the [Compose plugin](https://docs.docker.com/compose/install/linux/) if it isn't already included.

Confirm both are available:

```bash
docker --version
docker compose version
```

### 2. Get the code

```bash
git clone https://github.com/Code0I7/Aurum-Ex.git
cd Aurum-Ex
```

Оригинальный Aurum, если нужен именно он: `git clone https://github.com/Zproger/Aurum.git`

### 3. Configure your environment

Copy the template and open it in an editor:

```bash
cp .env.example .env
```

At minimum, change these two before going any further:

| Variable | What it does |
|---|---|
| `AURUM_POSTGRES_PASSWORD` | Password for Aurum's own Postgres container. The template ships with `change-me` on purpose — replace it with something real. |
| `AURUM_ADMIN_PASSWORD` | Пароль администратора для первого запуска. **Можно оставить пустым** — тогда приложение при первом открытии само попросит задать пароль в браузере, и он не окажется в файле на диске. Вход обязателен в любом случае: установки без пароля больше не бывает. |
| `AURUM_RECOVERY_KEY` | Аварийный ключ для сброса забытого пароля (`openssl rand -base64 48`). Пусто — сброс выключен. См. [Security & Self-Hosting](#-security--self-hosting). |

Everything else in `.env` (currency, CORS, the port Aurum listens on) has a sensible default and can be left alone for a first run.

### 4. Start it

```bash
docker compose up -d --build
```

This builds the backend and frontend images, starts Postgres, waits for it to report healthy, then starts the backend (which runs every database migration automatically — nothing to do by hand) and finally the frontend. First run takes a minute or two; after that, images are cached and it's seconds.

### 5. Open it

Visit **http://localhost:3000** (or whatever port you set via `AURUM_WEB_PORT` in `.env`). A default account and the standard expense/income categories are seeded automatically — there's nothing to configure before you can add your first transaction.

### 6. Check it's healthy (optional)

```bash
docker compose ps
```

All three containers (`db`, `backend`, `web`) should show `healthy`. If `web` or `backend` doesn't, check its logs:

```bash
docker compose logs backend
docker compose logs web
```

### Everyday operations

```bash
docker compose down          # stop everything, keep your data
docker compose up -d         # start it again later
docker compose down -v       # stop AND permanently delete your data — be sure
git pull && docker compose up -d --build   # update to newer code
```

Your data lives in a Docker named volume (`aurum_pgdata`), not in the repo folder — it survives `docker compose down`, image rebuilds, and `git pull`. It's only gone if you explicitly run `docker compose down -v` or delete the volume yourself. For anything short of that, use the in-app **Settings → Backup & Restore** to export a JSON snapshot of everything before making risky changes.

## 🔌 API

Everything Aurum's UI can do — adding transactions, managing accounts and budgets, importing a CSV,
tracking assets, exporting a backup — is also available as a plain JSON REST API at `/api`, so you
can script Aurum or connect it to other programs. See **[DOCS.md](DOCS.md)** for the full reference,
or open `/api/docs` on your running instance for interactive Swagger docs.

## 🔒 Security & Self-Hosting

**В отличие от оригинального Aurum, у Aurum-Ex есть собственный вход.** Оригинал полагался на HTTP Basic Auth в nginx: браузерное окно, без сессии, без выхода, с паролем в каждом запросе и в открытом виде в `.env`. Здесь вместо этого:

- **страница входа и серверная сессия.** Пароль хранится хешем (scrypt), сессия — в HttpOnly-куке, которую не прочитать скриптом со страницы. «Выйти» действительно обрывает сессию на сервере, а не просто стирает куку;
- **одна учётная запись на всё домохозяйство.** Это не многопользовательский режим: все входят под одним администратором и видят одни данные, а различаются участником в транзакции. Так семейный бюджет и устроен;
- **при первом открытии приложение само просит задать пароль.** Можно задать его заранее через `AURUM_ADMIN_PASSWORD`, но тогда он какое-то время лежит в файле на диске — надёжнее оставить переменную пустой и завести пароль в браузере;
- **забытый пароль** сбрасывается аварийным ключом `AURUM_RECOVERY_KEY` из `.env`, который знает только владелец сервера. Обычная смена пароля требует текущего, чтобы никто из домашних не заперся снаружи по случайности. Ключ не задан — сброс выключен целиком;
- **защита от перебора:** после `AURUM_MAX_FAILED_LOGINS` неудачных попыток вход блокируется на `AURUM_LOCKOUT_MINUTES` минут.

Что остаётся на вас:

- **TLS.** Aurum-Ex не терминирует HTTPS сам — нужен обратный прокси (Caddy, Traefik, nginx + Let's Encrypt). Публикуя экземпляр наружу, включите заодно `AURUM_SECURE_COOKIES=true`, чтобы кука сессии не уходила по открытому HTTP;
- **HTTP Basic Auth** (`AURUM_BASIC_AUTH_USER` / `AURUM_BASIC_AUTH_PASSWORD`) остался как необязательный второй барьер перед страницей входа. Раньше он был единственной защитой, теперь — дополнительный слой, и без него приложение уже не беззащитно.

If you find a security issue, please open a private report via GitHub's Security tab rather than a public issue.

## 🛠️ Tech Stack

- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Recharts
- **Backend:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2
- **Database:** PostgreSQL
- **Deployment:** Docker Compose (Postgres + FastAPI + nginx-served SPA)

## 🤝 Contributing

Это личный форк, и правки в нём подчинены задачам конкретного сценария использования. Прежде чем присылать сюда pull request, проверьте, не относится ли он к оригиналу: **исправления и улучшения базового Aurum правильнее отправлять в [Zproger/Aurum](https://github.com/Zproger/Aurum)** — так они попадут ко всем пользователям, а не только сюда. Файл [CONTRIBUTING.md](CONTRIBUTING.md) с описанием дев-окружения унаследован от оригинала и остаётся в силе.

## 📄 License

Aurum-Ex распространяется под той же лицензией, что и оригинал, — [PolyForm Noncommercial License 1.0.0](LICENSE). Форк не может смягчить условия оригинала и не пытается: файл [LICENSE](LICENSE) оставлен без единого изменения, вместе с обязательной строкой уведомления.

`Required Notice: Copyright ZProger (https://github.com/ZProger)`

Простыми словами: код можно читать, разворачивать у себя, изменять и использовать в любых личных, учебных и некоммерческих целях бесплатно и бессрочно. Нельзя — продавать его или изменённую версию, хостить как платный сервис для других и строить на нём коммерческий продукт. Это **не** OSI-совместимая открытая лицензия, а **source-available**. Точные условия — в файле [LICENSE](LICENSE).

Отдельное требование лицензии, которое касается любого, кто распространяет этот код дальше: вместе с копией нужно передавать текст лицензии (или ссылку на неё) **и** строку `Required Notice`, приведённую выше. Она относится к автору оригинала и не убирается ни при каком объёме доработок.

## 🙏 Благодарности

Весь фундамент этого проекта — чужая работа. **[ZProger](https://github.com/ZProger)** написал [Aurum](https://github.com/Zproger/Aurum): архитектуру, движок капитала, аналитику, докеризацию и двуязычный интерфейс, — и открыл исходный код, благодаря чему этот форк вообще стал возможен. Здесь переработана доменная модель под другой сценарий, но каркас, на котором всё держится, остался авторским.

Если проект оказался полезен, поддержать стоит именно автора оригинала: **[Donate via Lava](https://app.lava.top/782447112?tabId=donate)** — реквизиты его, а не форка. И звезда оригинальному репозиторию помогает ему больше, чем звезда этому.

---

<div align="center">

**Понравилась идея? Поставьте ⭐ [оригинальному Aurum](https://github.com/Zproger/Aurum) — проект вырос из него.**

</div>
