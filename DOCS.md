# Aurum-Ex API Documentation

Aurum-Ex exposes the same REST API its own frontend uses. Every action available in the UI — adding a
transaction with its receipt lines, creating an account, settling a debt with a person, importing a
spreadsheet, tracking an asset's price over years, setting a budget — can be done directly over HTTP.
This makes it possible to script Aurum-Ex, feed it from another program (a bank-sync job, a bot, a
shortcut on your phone), or pull your data into your own tools.

There is no SDK — it's a plain JSON REST API, callable with `curl`, any HTTP client library, or tools
like Postman/Insomnia.

> Interactive, always-up-to-date docs are also built into the backend itself: once your instance is
> running, open `http://<host>:<port>/api/docs` (Swagger UI) or `http://<host>:<port>/api/redoc`
> (ReDoc) for a live, "try it out" version of everything below. That spec is generated from the code,
> so where this file and `/api/docs` ever disagree, `/api/docs` is right.

## Table of Contents

- [Base URL & Authentication](#base-url--authentication)
- [Conventions](#conventions)
- [Errors](#errors)
- [Health Check](#health-check)
- [Accounts & Banks](#accounts--banks)
- [Credit Terms](#credit-terms)
- [Currencies & Exchange Rates](#currencies--exchange-rates)
- [Categories](#categories)
- [Tags](#tags)
- [Participants, Stores, Counterparties, Units](#participants-stores-counterparties-units)
- [Products & Receipt Lines](#products--receipt-lines)
- [Transactions](#transactions)
- [Settlements with People](#settlements-with-people)
- [Transfer Matching](#transfer-matching)
- [Recurring Transactions](#recurring-transactions)
- [Budgets](#budgets)
- [Plans & Work Periods](#plans--work-periods)
- [Goals](#goals)
- [Assets & Net Worth](#assets--net-worth)
- [Investments](#investments)
- [Crypto](#crypto)
- [Dashboard, Cash Flow & Reports](#dashboard-cash-flow--reports)
- [Insights & Advice](#insights--advice)
- [Settings](#settings)
- [Spreadsheet Import](#spreadsheet-import)
- [Backup & Restore](#backup--restore)
- [Recipes](#recipes)

## Base URL & Authentication

Aurum-Ex ships as three containers (Postgres, FastAPI backend, nginx-served frontend). The frontend
container reverse-proxies `/api/*` straight through to the backend, so **the API and the web UI share
the same host and port** — whatever you set `AURUM_WEB_PORT` to in `.env` (default `3000`):

```
http://<host>:<port>/api
```

For example, on a local install: `http://localhost:3000/api`. All endpoints below are relative to
this base URL — e.g. `GET /transactions` means `GET http://localhost:3000/api/transactions`.

### Auth

Unlike base Aurum, **Aurum-Ex has a login of its own**, and the API goes through it. One account per
household: everybody signs in as the same administrator and sees the same data, told apart by the
participant on a transaction rather than by a user row. There is no per-endpoint permission model and
no API keys — whoever can sign in can read, create, update and delete everything.

Signing in returns an **HttpOnly session cookie** named `aurum_session`; every request after that
carries it. With `curl`, that means a cookie jar:

```bash
# 1. Sign in once, keeping the session cookie in a file
curl -c /tmp/aurum.jar -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# 2. Every later call sends the jar back
curl -b /tmp/aurum.jar http://localhost:3000/api/accounts
```

The session lives `AURUM_SESSION_TTL_HOURS` hours (two weeks by default) and is stored server-side,
so `POST /auth/logout` really ends it rather than just dropping the cookie.

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/state` | Who you are and what state the install is in. Open to anyone — the login screen itself needs it. |
| `POST` | `/auth/setup` | First-run only: create the single account and sign in. `201`. `400` once setup is done. |
| `POST` | `/auth/login` | Sign in, setting the session cookie. `401` on a wrong password, `429` while locked out. |
| `POST` | `/auth/logout` | End the current session server-side and clear the cookie. `204`. |
| `POST` | `/auth/password` | Change the password; requires `current_password`. `204`. |
| `POST` | `/auth/username` | Change the login name; requires `current_password`. `204`. |
| `POST` | `/auth/recover` | Reset a forgotten password with `AURUM_RECOVERY_KEY`. `204`. `400` if no key is configured. |
| `GET` | `/auth/suggest-username` | A random pronounceable name, for people who would rather not reuse `admin`. |

**`GET /auth/state` response:**

```json
{ "setup_complete": true, "authenticated": false, "username": null, "recovery_available": true }
```

**Bodies:** `/auth/setup` takes `{"username": "admin", "password": "…", "language": "en",
"currency": "USD"}` (`username` defaults to `admin`; `language`/`currency` are optional and seed the
new install's settings). `/auth/login` takes `{"username", "password"}`. `/auth/password` takes
`{"current_password", "new_password"}`, `/auth/username` takes `{"current_password", "new_username"}`,
`/auth/recover` takes `{"recovery_key", "new_password"}`. A password is at least 8 characters.

**Brute-force protection:** after `AURUM_MAX_FAILED_LOGINS` failures in a row, login is refused for
`AURUM_LOCKOUT_MINUTES` minutes. A script that retries a wrong password in a loop will lock the
household out of its own ledger, so handle `429` by stopping rather than by waiting a second.

`GET /api/health` is the only endpoint outside this entirely — it exists for Docker healthchecks and
uptime monitors, and never touches your data.

### The optional second layer

`AURUM_BASIC_AUTH_USER` / `AURUM_BASIC_AUTH_PASSWORD` put HTTP Basic Auth on nginx in *front* of the
whole app, UI and API alike. It is an extra barrier, not the app's login: with it configured, a
request needs both the Basic credentials (`-u user:password`) and the session cookie. `/api/health`
stays open through it.

## Conventions

- **Format:** all request and response bodies are JSON (`Content-Type: application/json`). The only
  exception is [Spreadsheet Import](#spreadsheet-import), which takes `multipart/form-data`.
- **IDs:** integer, auto-incrementing, assigned by the server. Transactions also carry a `uuid`,
  stable across backup/restore.
- **Money fields** (`amount`, `monthly_limit`, `value`, …): decimal numbers as JSON numbers or
  strings, generally up to 14–18 digits with 2 decimal places. Quantities and crypto amounts allow
  more decimals, noted where they do.
- **Currency and conversion.** Every account, asset and holding has its own currency. A transaction's
  `amount` is in its own `currency`, and the server derives two read-only companions: `exchange_rate`,
  the central-bank rate for that currency **on the transaction's own date**, and `amount_base`, the
  amount in the install's currency. Totals are summed over `amount_base`, never over `amount` — one
  €100 purchase must not enter a rouble total as 100.
  If no rate is known for that date, both come back `null` and the transaction is **left out of
  totals** rather than counted at 1:1. It is still stored and still shown: losing the record is worse
  than not knowing its rate, and a rate for a past day never changes, so fetching it later and
  recomputing is recording history for the first time rather than rewriting it.
- **Dates:** `YYYY-MM-DD` (ISO 8601 date, no time component). Timestamps (e.g. backup `exported_at`)
  are full ISO 8601 datetimes.
- **Order within a day:** transactions carry `day_order`. The date decides the day, this decides the
  sequence inside it — the running `balance_after` depends on it, and a bad order can show a dip
  below zero on a day that never had one.
- **Colors:** 6-digit hex strings, e.g. `"#4f46e5"`.
- **Partial updates:** every `PATCH` endpoint only touches the fields you actually send — omit a
  field and it's left unchanged. This matters for fields whose "clear this" value is `null`: sending
  `{"parent_id": null}` explicitly clears a category's parent, while omitting `parent_id` entirely
  leaves it as-is.
- **Enums** are plain lowercase strings — see each resource's table below for the valid values.

## Errors

Standard HTTP status codes:

| Code | Meaning |
|---|---|
| `200` / `201` | Success (`201` on `POST` that creates a resource) |
| `204` | Success, no response body (deletes, and the auth endpoints that only change state) |
| `400` | Invalid request — a business rule was violated (e.g. wrong category kind, duplicate budget) |
| `401` | No session, or an invalid one. Sign in again. |
| `404` | Resource not found |
| `409` | The request would collide with something that already exists (e.g. moving an asset valuation onto a date that already has one) |
| `422` | Request body failed schema validation (wrong type, missing required field, out-of-range value) |
| `428` | The install has no password yet — run `POST /auth/setup` first. Distinct from `401` on purpose: "sign in" and "set a password" are different instructions. |
| `429` | Too many failed logins; locked out for `AURUM_LOCKOUT_MINUTES` |

Error bodies follow FastAPI's default shape:

```json
{ "detail": "Category 'Salary' is a income category and cannot be used for a expense transaction" }
```

`422` validation errors carry a `detail` array with one entry per invalid field instead of a single
string.

## Health Check

### `GET /api/health`

No auth required. Returns `{"status": "ok", "version": "…"}` — `version` is the running app's
version, the same value shown in the UI under Settings. Use this to check the backend is up before
hitting anything else.

## Accounts & Banks

An account is a place money lives — a bank account, a card, a cash wallet, a credit line. Every
transaction belongs to exactly one account (transfers touch two). Balances are **derived** from the
opening balance plus every transaction on the account, not stored — there's no "set balance" endpoint.

**`AccountKind`:** `checking` · `savings` · `credit_card` · `cash` · `investment` · `crypto` ·
`loan` (an instalment plan or a cash loan, no plastic) · `other`

**`AccountNature`:** `asset` · `liability`. Derived from `kind` when you don't send it: a credit card
or a loan is a liability, everything else an asset. A liability's minus means debt, not a typo, which
is why `allow_negative` also defaults from it.

| Method | Path | Description |
|---|---|---|
| `GET` | `/accounts` | List accounts with live balance. `?include_archived=true` to include archived ones (excluded by default). |
| `POST` | `/accounts` | Create an account. |
| `PATCH` | `/accounts/{id}` | Update an account (partial). Set `is_archived: true` to archive instead of deleting. |
| `DELETE` | `/accounts/{id}` | Delete an account **and every transaction on it** — irreversible. |
| `GET` | `/banks` | List banks, for grouping accounts. |
| `POST` | `/banks` | Create a bank: `{"name": "…", "color": "#…", "sort_order": 0}`. |
| `PATCH` | `/banks/{id}` | Rename/recolor/reorder a bank. |

**Create/update body:**

```json
{
  "name": "Checking",
  "kind": "checking",
  "nature": null,
  "bank_id": 2,
  "currency": "USD",
  "opening_balance": 1200.00,
  "opening_date": "2022-01-01",
  "allow_negative": null,
  "color": "#4f46e5"
}
```

- `name`: required, 1–100 chars.
- `kind`: optional, defaults to `checking`.
- `nature` / `allow_negative`: optional — derived from `kind` when omitted (see above).
- `bank_id`: optional. Grouping only; an account needs no bank.
- `currency`: optional 3-letter code. **Omit it and the install's own currency is used** — not a
  hardcoded dollar. Used for real conversion, see [Conventions](#conventions).
- `opening_balance` / `opening_date`: what was on the account before the ledger starts, and when.
  This is the reason a migrated history doesn't have to book its starting money as income. An account
  with no `opening_date` is left out of day-resolution cash-flow series: a month "before records
  began" has no day of its own, and pinning the balance to the 1st would invent an event.
- `color`: optional hex color.
- `is_archived` (update only): archive/unarchive without deleting. An archived account is hidden
  from the default account list but its transactions and balance remain intact.

**Response** (`AccountWithBalance`):

```json
{
  "id": 1, "name": "Checking", "kind": "checking", "nature": "asset",
  "bank_id": 2, "bank": { "id": 2, "name": "…", "color": "#…", "sort_order": 0 },
  "currency": "USD", "opening_balance": "1200.00", "opening_date": "2022-01-01",
  "allow_negative": false, "color": "#4f46e5", "is_archived": false,
  "balance": "1523.40", "balance_base": "1523.40",
  "reserved": "300.00", "available": "1223.40", "transaction_count": 412
}
```

`balance` is in the account's own currency, `balance_base` in the install's. `reserved` is what goals
linked to this account have claimed — the money hasn't moved anywhere, part of it is just promised —
and `available` is the balance minus that.

## Credit Terms

A card or an instalment plan has terms a plain account doesn't: a rate, a limit, a grace period, a
payment day. They live beside the account rather than on it, because most accounts have none.

| Method | Path | Description |
|---|---|---|
| `GET` | `/credits` | Terms for every account that has them, with computed debt and headroom. |
| `GET` | `/credits/summary` | Total debt and estimated monthly interest across all of them. |
| `GET` | `/accounts/{id}/credit-terms` | One account's terms. `404` if it has none. |
| `PUT` | `/accounts/{id}/credit-terms` | Create or replace one account's terms (including its whole `rates` list). |
| `DELETE` | `/accounts/{id}/credit-terms` | Drop the terms; the account itself stays. |
| `POST` | `/credits/plan` | Pay-off calculator — see below. Pure arithmetic, writes nothing. |

**Write body** (`PUT`): `annual_rate_percent`, `credit_limit`, `grace_days`, `payment_day` (1–31),
`minimum_payment`, `minimum_payment_percent`, `opened_on`, `closes_on`, `notes`, and `rates` — a list
of `{"name", "percent", "condition"}` for cards whose rate depends on what you bought (purchases,
cash withdrawal, instalments).

**Read** adds `account_name`, `account_currency`, `debt`, `available`, `used_percent`,
`estimated_monthly_interest` and `minimum_payment_due`. Interest is an **estimate**, and the UI marks
it with "≈": banks compute it in ways no single formula reproduces, and pretending otherwise would be
worse than admitting it. Interest actually charged is entered as a normal transaction.

**`POST /credits/plan`** takes `{"amount", "annual_rate_percent", "minimum_percent",
"minimum_floor", "fixed_payment", "target_months", "fee_percent", "fee_fixed"}` and answers three
questions at once: paying the minimum, paying a recommended amount, and paying a fixed sum. Each
outcome carries `payment`, `months`, `total_paid`, `total_interest`, a month-by-month `schedule`, and
`never_closes` — because a minimum payment below the interest accrued genuinely never closes the
debt, and saying so is the point of the endpoint.

## Currencies & Exchange Rates

The install has one base currency (Settings → `currency`). Everything else is a watched currency with
a daily rate, fetched from the Russian Central Bank's published rates. Rates are per date and
immutable once published, which is what makes `amount_base` reproducible.

| Method | Path | Description |
|---|---|---|
| `GET` | `/currencies` | Watched currencies with their latest rate. |
| `POST` | `/currencies` | Start watching one: `{"code": "EUR"}`. |
| `DELETE` | `/currencies/{code}` | Stop watching it. `400` if accounts or transactions still use it. |
| `GET` | `/currencies/rates` | Latest rate per currency, with the previous one for comparison and `in_use`. |
| `POST` | `/currencies/rates/sync` | Fetch rates for one day. `?on_date=` (default today). |
| `POST` | `/currencies/rates/backfill` | Fill in rates for the dates your own transactions need, and recompute the `amount_base` of the ones that were missing it. Reports `remaining` so you can call it again. |
| `GET` | `/currencies/{code}/history` | Rate series. `?start_date=` and `?end_date=` required, `?monthly=true` for month steps. Missing days are fetched on the way. |

`source_unavailable` in a history response means the Central Bank couldn't be reached — what's stored
is still returned, rather than failing the whole request.

## Categories

Categories classify transactions as income or expense, and nest to **any depth** — "Groceries →
Dairy → Cheese" is the ordinary case, not an edge one. A parent and its children always share a
`kind`. A handful of default categories are seeded on first run and can't be deleted while anything
points at them (`is_default: true`), though they can be renamed, recolored and reordered.

**`CategoryKind`:** `income` · `expense`

| Method | Path | Description |
|---|---|---|
| `GET` | `/categories` | List categories, sorted by `sort_order`. `?kind=income` or `?kind=expense` to filter. |
| `GET` | `/categories/totals` | Amount and transaction count per category — its own, and including descendants. `?start_date=&end_date=` (default: all time). |
| `GET` | `/categories/{id}/usage` | What deleting it would touch: `transactions`, `children`, `descendants`, `descendant_transactions`. |
| `POST` | `/categories` | Create a category (or subcategory, via `parent_id`). |
| `PATCH` | `/categories/{id}` | Update a category (partial). |
| `DELETE` | `/categories/{id}` | Delete a category. For a default (`is_default: true`) one, fails with `400` if any transaction or split still points at it. |

**Create body:**

```json
{
  "name": "Groceries",
  "kind": "expense",
  "icon": "shopping-cart",
  "color": "#22c55e",
  "sort_order": 0,
  "parent_id": null,
  "is_watched": false
}
```

- `name`: required, 1–100 chars.
- `kind`: required, `income` or `expense`. Fixed at creation — there's no way to flip a category's
  kind afterward (create a new one instead), and it is the one field `PATCH` doesn't accept.
- `icon`: optional, free-form string (the frontend maps these to an icon set).
- `color`: required hex color.
- `sort_order`: optional int controlling display order, defaults to `0`.
- `parent_id`: optional, any existing category of the same `kind`. The server rejects a cycle (a
  category can't become its own descendant).
- `is_watched`: puts the category on the [watchlist](#plans--work-periods).

**Update** accepts the same fields except `kind`, all optional, plus `apply_style_to_children`:
send it with a new `color`/`icon` to push the same style down the whole branch in one call. To turn a
subcategory back into a top-level category, send `"parent_id": null` explicitly — omitting the field
leaves the existing parent as-is.

**Response** (`CategoryRead`): the create fields plus `id` and `is_default`.

Totals and reports **roll up** a branch: a category's figure includes its descendants, and the
difference between "own" and "with descendants" is how much was dropped in the parent without
picking a subcategory.

## Tags

Free-form labels a transaction can carry any number of. Case-insensitive dedup on creation: posting
`"Georgia"` when `"georgia"` already exists returns the existing tag instead of making a duplicate.

| Method | Path | Description |
|---|---|---|
| `GET` | `/tags` | List all tags, alphabetically. |
| `POST` | `/tags` | Create a tag (or return the existing one, case-insensitive match). |
| `DELETE` | `/tags/{id}` | Delete a tag — removes it from every transaction that had it. |

**Create body:** `{"name": "Vacation"}` (1–50 chars).

**Response** (`TagRead`): `{"id": 1, "name": "Vacation"}`.

## Participants, Stores, Counterparties, Units

Four small directories that give a transaction its other dimensions. All four are filled in as you
go rather than set up in advance, and all four answer a different question.

| Directory | Question it answers |
|---|---|
| **Participants** | Who was this income or expense *for*? Family members, and pets. |
| **Stores** | Where was it bought? |
| **Counterparties** | Which person or organisation was on the other side of a settlement? |
| **Units** | How is a product measured, and how does that compare? |

All four take the same four calls:

| Method | Path | Description |
|---|---|---|
| `GET` | `/participants` | List participants. `?include_archived=true`. |
| `POST` | `/participants` | Create one: `{"name", "kind", "color"}`. |
| `PATCH` | `/participants/{id}` | Update (partial), `is_archived` included. |
| `DELETE` | `/participants/{id}` | Delete. `400` while transactions still point at it. |
| `GET` | `/stores` | List stores. `?include_archived=true`. |
| `POST` | `/stores` | Create one: `{"name", "location", "group_name", "notes"}`. |
| `PATCH` | `/stores/{id}` | Update (partial), `is_archived` included. |
| `DELETE` | `/stores/{id}` | Delete. `400` while transactions still point at it. |
| `GET` | `/counterparties` | List counterparties. `?include_archived=true`. |
| `POST` | `/counterparties` | Create one: `{"name", "group_name", "notes"}`. |
| `PATCH` | `/counterparties/{id}` | Update (partial), `is_archived` included. |
| `DELETE` | `/counterparties/{id}` | Delete. `400` while settlements still point at it. |
| `GET` | `/units` | List units of measure. |
| `POST` | `/units` | Create one — see `factor` below. |
| `PATCH` | `/units/{id}` | Update (partial). |
| `DELETE` | `/units/{id}` | Delete. `400` while products or receipt lines still use it. |

**`ParticipantKind`:** `person` · `pet`.
**`UnitKind`:** `mass` (base: gram) · `volume` (base: millilitre) · `count` (base: piece) ·
`length` (base: metre) · `service` (unmeasured, quantity is always 1).

`GET /participants`, `/stores` and `/counterparties` take `?include_archived=true`; each read carries
a `usage` count, and a store also carries `spent_total` / `spent_year`. Archiving is the normal way
to retire an entry — `DELETE` is refused with `400` while anything still points at it.

**A unit needs its `factor`** — how many base units it is worth — and it must be greater than zero:
"a jar" compares to nothing on its own, "a jar = 400 g" lines up beside kilograms. Zero would turn
price-per-base-unit into a division by zero, so it's rejected.

```json
// POST /units
{ "name": "jar", "kind": "mass", "factor": 400, "sort_order": 0 }
```

## Products & Receipt Lines

A product is "what was bought", as opposed to a category's "where the money went". Ten receipts with
the word "bread" are ten unrelated strings; ten lines pointing at one product are a price curve, and
that curve is the whole reason the directory exists.

| Method | Path | Description |
|---|---|---|
| `GET` | `/products` | List products with purchase stats. `?include_archived=true`. |
| `GET` | `/products/suggest` | `?q=` — type-ahead while filling in a receipt line. |
| `GET` | `/products/{id}/prices` | Price history, converted to the base unit. |
| `POST` | `/products` | Create a product: `{"name", "unit_id", "barcode", "notes"}`. |
| `PATCH` | `/products/{id}` | Update (partial). `is_archived` to retire it. |
| `DELETE` | `/products/{id}` | Delete. `400` while receipt lines still reference it. |

**Products deliberately have no category.** It used to be copied onto every receipt line, where no
report ever read it: money is counted by the transaction's category and its splits. "What was bought"
and "where the money went" are different questions, and one receipt is divided between categories
with splits.

`ProductRead` carries `last_quantity`, `last_unit_id`, `last_pack_size`, `last_pack_unit_id` — the
shape of the previous purchase, so the next receipt line can prefill itself. Bread is bought by the
piece, milk by the litre, and retyping that every time is pointless.

**`GET /products/{id}/prices` response** groups the series by unit kind, each point carrying
`price_per_base_unit` alongside the raw `quantity`/`amount`, the store, and the transaction it came
from. `unmeasured` counts the purchases that had no unit and therefore can't join a curve.

Receipt lines themselves are written as part of a transaction — see `items` in
[Transactions](#transactions).

## Transactions

The core resource.

**`TransactionType`:**

| Value | Meaning |
|---|---|
| `income` | Money earned. |
| `expense` | Money spent. |
| `transfer` | Between two of your own accounts. Neither income nor expense. |
| `external_in` | Money received from a person: a gift, a loan taken, a repayment, money passing through you. |
| `external_out` | Money handed to a person, the same four ways round. |

The last two exist because a bank statement cannot tell a spouse handing over grocery money from a
friend borrowing until payday, and the two mean opposite things. What separates them is
`settlement_kind`:

**`SettlementKind`** (only on `external_in` / `external_out`):

| Value | Meaning |
|---|---|
| `gift` | Not coming back. Never enters "who owes whom". |
| `loan_out` | You lent — you are owed. |
| `loan_in` | You borrowed — you owe. |
| `repayment` | Settling a debt that already existed. |
| `transit` | Money passed through you: received from one person, handed to another. Creates no debt, like a gift, but means something different — a whip-round for a shared present was never income and never generosity. |

Whether an `external_out` counts as **spending** is answered in [Settings](#settings): money given
away for good always does, money lent does when `lending_is_spending` is on (the default). Neither is
ever income.

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions` | Paginated, filterable list. See query params below. |
| `GET` | `/transactions/years` | Every year with data (plus the current year), for a year picker. Returns `[2024, 2025, 2026]`. |
| `GET` | `/transactions/similar` | `?date=&type=&amount=&description=` — is this already recorded today? For a duplicate warning while typing. |
| `POST` | `/transactions` | Create one transaction. |
| `POST` | `/transactions/bulk` | Create up to 5000 transactions in one all-or-nothing batch (CSV import). |
| `PATCH` | `/transactions/{id}` | Update a transaction (partial). |
| `DELETE` | `/transactions/{id}` | Delete a transaction. |
| `POST` | `/transactions/{id}/reorder` | Move it to `{"position": n}` within its day. |
| `POST` | `/transactions/reorder-block` | Move a whole group of same-day rows: `{"ids": [...], "position": n}`. |

`/transactions/similar` is a question asked **before** writing, not a refusal at write time:
refusing would also have to refuse the spreadsheet import, recurring posting and any script using
this API, where repeats are legitimate and expected. Only a human typing benefits from being asked.

### `GET /transactions` query params

| Param | Type | Notes |
|---|---|---|
| `year` | int | `2000`–`2100` |
| `month` | int | `1`–`12` |
| `start_date` / `end_date` | date | Inclusive range, combinable with `year`/`month` |
| `account_id` | int | Matches **both** sides of a transfer, so a per-account statement shows money that arrived as well as money that left |
| `bank_id` | int | Every account of one bank at once — handy when a bank has both a card and an instalment plan |
| `category_id` | int | Includes the whole branch below it, and split lines that point into it |
| `tag_id` | int | |
| `type` | `TransactionType` | |
| `participant_id` | int | |
| `no_participant` | bool | Default `false`. Rows where the participant was forgotten. A separate flag, not a magic id: `0` or `-1` would one day collide with a real one |
| `store_id` | int | |
| `counterparty_id` | int | |
| `include_excluded` | bool | Default `true` — excluded rows exist precisely to stay visible |
| `search` | string | Case-insensitive substring over description and merchant |
| `sort` | `date_desc`\|`date_asc`\|`amount_desc`\|`amount_asc` | Default `date_desc` |
| `page` | int | Default `1` |
| `page_size` | int | Default `20`, max `200` |

**Response** (`TransactionPage`):

```json
{
  "items": [ /* TransactionRead[] */ ],
  "total": 143,
  "page": 1,
  "page_size": 20
}
```

### Create body (`TransactionCreate`)

```json
{
  "account_id": 1,
  "category_id": 4,
  "transfer_account_id": null,
  "type": "expense",
  "amount": 42.50,
  "currency": null,
  "description": "Groceries",
  "merchant": "Corner shop",
  "date": "2026-08-29",
  "participant_id": 2,
  "store_id": 5,
  "counterparty_id": null,
  "transit_party_id": null,
  "settlement_kind": null,
  "is_excluded": false,
  "day_order": 0,
  "tag_ids": [3, 7],
  "splits": null,
  "counterparty_splits": null,
  "items": null
}
```

Field rules, enforced server-side:

- `account_id`: required, the account the money moves through.
- `type`: required. Drives which other fields are valid:
  - `income` / `expense`: `category_id` optional but **must** point at a category of the matching
    `kind` if given (an `income` transaction can't use an `expense` category). `transfer_account_id`
    must be omitted.
  - `transfer`: `transfer_account_id` is **required** and must differ from `account_id`.
    `category_id` must be omitted — transfers aren't categorized. `splits` aren't valid either. When
    the two accounts hold different currencies, `transfer_amount` is **required**: that is what
    arrived on the other side, and the difference after conversion is what the transfer cost.
  - `external_in` / `external_out`: `settlement_kind` says whether it comes back;
    `counterparty_id` (or `counterparty_splits`) says who it was with. `transit_party_id` records
    who money in transit was ultimately meant for.
- `amount`: required, `> 0` (direction comes from `type`, never from a minus sign), up to 18 digits,
  2 decimal places.
- `currency`: optional 3-letter code. Omitted, the account's currency is used. `exchange_rate` and
  `amount_base` are then derived from the rate on `date` — see [Conventions](#conventions).
- `description`: optional, up to 255 chars. Auto-capitalized server-side (first letter uppercased),
  so a mixed-case history reads evenly.
- `merchant`: optional, up to 150 chars.
- `date`: required.
- `is_excluded`: keeps the row in history and out of every total — for a mistaken transfer or a
  duplicated line. Deleting such a row would be wrong (it happened); counting it would be wrong too.
- `day_order`: position within the day, assigned automatically when omitted.
- `tag_ids`: optional list of existing tag IDs. Unknown IDs return `400`.
- `splits`, `counterparty_splits`, `items`: see below.

**Update** (`TransactionUpdate`) accepts the same fields, all optional, with the same
type/category/transfer/split consistency rules applied to the *effective* (merged) values. `tag_ids`:
omit to leave tags untouched; send (even `[]`) to replace the full set. Same for `splits`,
`counterparty_splits` and `items` — send `[]` with a `category_id` to turn a split transaction back
into a normal single-category one.

**Response** (`TransactionRead`): the input fields plus `id`, `uuid`, `amount_base`,
`exchange_rate`, `transfer_currency`, `transfer_amount_base`, the nested `account` / `transfer_account`
(`AccountRead`), `category` (`CategoryRead` or `null`), `tags`, `splits`, `counterparty_splits`,
`items`, and `balance_after` — the account's running balance after this row, computed over the
account's whole history rather than the visible page, because a balance shown on a filtered list
where earlier rows are hidden is a wrong number.

### Splitting a transaction across categories

One purchase covering several categories is one transaction divided between them, not several
transactions:

```json
{
  "account_id": 1,
  "type": "expense",
  "amount": 84.20,
  "description": "Grocery run",
  "date": "2026-08-29",
  "splits": [
    { "category_id": 12, "amount": 60.00, "note": "Sweets" },
    { "category_id": 13, "amount": 24.20, "note": "Household" }
  ]
}
```

Rules, enforced on create and on update (against the row as it would look *after* the change):

- `category_id` on the transaction itself **must be omitted** — the split entries carry the
  categories instead.
- Not valid on a `transfer`.
- At least 2 entries — a single split is `category_id` with extra steps.
- Each entry needs a `category_id` of the transaction's own kind and an `amount` (`> 0`, up to 14
  digits/2 decimals); `note` is optional, up to 200 chars.
- The amounts **must sum exactly** to the transaction's `amount`, or the request is rejected
  with `400`.
- The categories may come from **any branches**. There used to be a shared-root requirement, and it
  described a convenient half of life rather than life: one receipt holds things from different
  branches routinely, and the rule forced either a lie about the category or two transactions for one
  purchase. Reports don't suffer — each share is still counted in its own category and still rolls up
  into its own root; a transaction simply may now touch more than one root.

Aggregation endpoints are split-aware: `/dashboard/summary`'s `spending_by_category` and
`/reports/category-ranking` count a split transaction under every category it actually touches.

### Splitting between people

The second, independent axis: three people repaid a debt with one transfer. In the bank statement
that's one operation, and three rows in the app would stop matching the statement.

```json
{
  "account_id": 1, "type": "external_in", "settlement_kind": "repayment",
  "amount": 3000, "date": "2026-08-29",
  "counterparty_splits": [
    { "counterparty_id": 4, "amount": 1000 },
    { "counterparty_id": 5, "amount": 2000 }
  ]
}
```

Only valid on `external_in` / `external_out`; replaces `counterparty_id` rather than supplementing
it; at least two entries; amounts must sum exactly to `amount`.

### Receipt lines

`items` is "what was in the bag". They sit alongside `splits` and are a different thing: a split
divides the money between categories and must add up to the total, a line describes a purchase and
has to add up to nothing. An empty `items` list is a perfectly normal receipt.

```json
{
  "items": [
    { "product_id": 8, "name": "Milk", "quantity": 1, "unit_id": 3,
      "pack_size": 950, "pack_unit_id": 2, "price": 89.90, "amount": 89.90, "note": null }
  ]
}
```

`pack_size`/`pack_unit_id` are for goods sold by the pack — one bottle of 950 ml — so the price
curve can compare it with a litre. `price` is per unit, `amount` the line total; both optional, since
a line is often worth recording even when only one of them is known.

### Bulk create (`POST /transactions/bulk`)

Used by the CSV import wizard, but callable directly for any bulk load (e.g. syncing from a bank
export tool). All rows are validated **before** any is inserted — one bad row fails the whole
request with no partial import.

```json
{ "items": [ /* 1–5000 TransactionCreate objects */ ] }
```

Response: `{"created": 250}`.

## Settlements with People

Read-only views over `external_in` / `external_out` transactions. Nothing is created here: a
settlement is a transaction, and these endpoints only add up what the transactions say.

| Method | Path | Description |
|---|---|---|
| `GET` | `/settlements` | Per person: `received`, `given`, `owed_to_me`, `owed_by_me`, `balance`, `operations`, `last_date`. |
| `GET` | `/settlements/summary` | Totals: `owed_to_me`, `owed_by_me`. |
| `GET` | `/settlements/transit` | Money that passed through you: `passed_through` and `held` (received and not yet handed on). |
| `GET` | `/settlements/transit-by-person` | The same, per person. `?year=&month=` to narrow. |

**Turnover and debt are different things**, and the response keeps them apart on purpose. Somebody
may have handed over half a million for groceries across four years and owe nothing: `received` is
turnover, while `owed_to_me` / `owed_by_me` count only what was marked `loan_out` / `loan_in` and
hasn't been repaid.

Amounts come back as **strings** here, already rounded for display, and `mixed_currencies` warns when
a person's rows span currencies — in which case the one total is a sum of unlike things and the UI
says so rather than quietly adding them.

## Transfer Matching

A statement imported from two cards contains the same transfer twice: once as money leaving, once as
money arriving. These endpoints find such pairs and merge them into one transfer.

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions/transfer-matches` | Pairs that look like two halves of one transfer, each as `keep` + `drop`. |
| `GET` | `/transactions/transfer-matches/check` | `?type=&account_id=&amount=&date=` (plus optional `transfer_account_id`, `transfer_amount`) — would the row being typed pair with an existing one? |
| `POST` | `/transactions/transfer-matches/merge` | `{"first_id", "second_id"}` — turn the pair into one transfer. |
| `POST` | `/transactions/transfer-matches/dismiss` | `{"first_id", "second_id"}` — "these two are not a pair", remembered so it stops being offered. |

As with duplicate detection, `check` is a question before writing rather than a refusal while
writing: two legitimate transfers of the same amount on the same day do happen.

## Recurring Transactions

Templates for bills/income that repeat on a schedule. **Nothing posts automatically in the
background** — a transaction is only created when you call the `/post` endpoint (or click "Post" in
the UI). This is deliberate: a missed week never silently back-fills a pile of transactions that
might never have happened.

**`RecurringFrequency`:** `weekly` · `monthly` · `yearly`

| Method | Path | Description |
|---|---|---|
| `GET` | `/recurring` | List all recurring templates, with computed due-date info. |
| `POST` | `/recurring` | Create a template. |
| `PATCH` | `/recurring/{id}` | Update a template (partial). Set `is_active: false` to pause. |
| `DELETE` | `/recurring/{id}` | Delete a template (does not touch already-posted transactions). |
| `POST` | `/recurring/{id}/post` | Create a real transaction from the template, dated today, and advance the schedule. |

**Create body:**

```json
{
  "account_id": 1,
  "category_id": 4,
  "type": "expense",
  "amount": 15.99,
  "description": "Streaming",
  "notes": null,
  "frequency": "monthly",
  "anchor_date": "2026-01-05"
}
```

`anchor_date` is the first due date; each `/post` call advances `last_posted_date` and recomputes
`next_due_date` (monthly clamps to the shortest month, e.g. day 31 → day 28/29/30; yearly Feb 29
falls back to Feb 28 in non-leap years).

**Response** (`RecurringTransactionRead`) adds computed fields: `next_due_date`, `is_due` (boolean),
`days_until_due` (negative if overdue), plus denormalized `account_name`/`category_name`/etc. for
display without extra lookups.

## Budgets

One monthly spending limit per **expense** category (income categories can't be budgeted; each
category can have at most one budget). A budget on a branch sees its subcategories too.

| Method | Path | Description |
|---|---|---|
| `GET` | `/budgets` | List all budgets. |
| `GET` | `/budgets/status` | Budgets vs. actual spend for a month. `?year=&month=` (default: current month). |
| `POST` | `/budgets` | Create a budget. `400` if the category already has one, or isn't an expense category. |
| `PATCH` | `/budgets/{id}` | Update `monthly_limit`. |
| `DELETE` | `/budgets/{id}` | Delete a budget. |

**Create body:** `{"category_id": 4, "monthly_limit": 500}`.

**`GET /budgets/status` response:**

```json
{
  "year": 2026,
  "month": 8,
  "items": [
    {
      "budget_id": 1,
      "source": "budget",
      "category_id": 4,
      "category_name": "Groceries",
      "category_color": "#22c55e",
      "category_icon": "shopping-cart",
      "monthly_limit": "500.00",
      "spent": "612.30",
      "remaining": "-112.30",
      "percent": 122.46,
      "is_over_budget": true
    }
  ]
}
```

`percent` can exceed `100` on purpose — clamp it client-side if you're rendering a progress bar.
`source` is `"budget"` for a real budget row and `"plan"` for a ceiling implied by a
[plan](#plans--work-periods), whose `budget_id` is then `null`.

## Plans & Work Periods

A plan describes what the year is supposed to look like. It's written once and expands itself: a
monthly line, a daily line times the days in the month, a one-off in its own month. Each plan carries
`periods` — the amount and the date it starts applying from — because prices change in jumps, and the
correct record is "it became this much from this month", not a retroactively rewritten past.

**`PlanFrequency`:** `one_off` · `day` · `week` · `month` · `year`
**`PlanMonthDay`** (for monthly plans): `day_of_month` · `nth_weekday` · `last_day` ·
`first_workday` · `last_workday`

| Method | Path | Description |
|---|---|---|
| `GET` | `/plans` | List plans with their periods. |
| `POST` | `/plans` | Create a plan. `periods` is required and needs at least one entry. |
| `PATCH` | `/plans/{id}` | Update (partial). Sending `periods` replaces the whole list. |
| `DELETE` | `/plans/{id}` | Delete a plan. |
| `GET` | `/plans/overview` | `?year=` — plan vs. actual per category per month, with income/expense/free totals. |
| `GET` | `/plans/watchlist` | `?year=` — the categories flagged `is_watched`, month by month, beside last year's total. |

`workdays_only` on a daily plan counts working days from the work periods below instead of calendar
days, so February recalculates itself. A plan is stopped with an end date on its period, not by
deletion — otherwise last year's plan-vs-actual comparison stops being true.

**Work periods** record hours actually worked per month, which is where the hourly rate comes from —
the one used for "what did this purchase cost in working time".

| Method | Path | Description |
|---|---|---|
| `GET` | `/work-periods` | `?year=` — hours and workdays per month. |
| `PUT` | `/work-periods` | Upsert one month: `{"year", "month", "hours", "workdays", "participant_id"}`. |
| `DELETE` | `/work-periods/{id}` | Remove one month. |
| `GET` | `/work-periods/hourly-rates` | Earned per hour, per month and overall. |

There is deliberately no built-in working calendar: everybody's schedule differs, and the number you
entered yourself is always right.

## Goals

Savings goals with a running contribution log. `current_amount` is always the sum of every logged
contribution — there's no separate "set balance" call. Linking a goal to an account makes that
account report `reserved` and `available`: the money hasn't moved anywhere, part of it is promised.

**`GoalStatus`:** `active` · `achieved` (saved up and spent as intended) · `cancelled` (changed your
mind, the reservation is released)

| Method | Path | Description |
|---|---|---|
| `GET` | `/goals` | List goals with computed progress. |
| `GET` | `/goals/reservations` | Per account: which goals reserve how much of it. |
| `POST` | `/goals` | Create a goal. |
| `PATCH` | `/goals/{id}` | Update `name`, `target_amount`, `started_on`, `planned_on`, `account_id`, `status`, `closed_at`. |
| `DELETE` | `/goals/{id}` | Delete a goal and its contribution log. |
| `GET` | `/goals/{id}/contributions` | The log, oldest first, each with a `running_total`. |
| `POST` | `/goals/{id}/contributions` | Log a contribution (or a withdrawal). |
| `PATCH` | `/goals/{id}/contributions/{contribution_id}` | Correct one entry. |
| `DELETE` | `/goals/{id}/contributions/{contribution_id}` | Remove one entry. |

**Create body:** `{"name": "Emergency fund", "target_amount": 10000, "started_on": "2026-01-01",
"planned_on": "2027-01-01", "account_id": 2}` — everything but `name` and `target_amount` optional.

**Add contribution:** `{"amount": 250, "date": "2026-08-29", "note": "Bonus", "account_id": 2}`.
`amount` may be negative (a withdrawal against the goal) but not zero.

**Response** (`GoalRead`):

```json
{
  "id": 1, "name": "Emergency fund", "target_amount": "10000.00",
  "started_on": "2026-01-01", "planned_on": "2027-01-01",
  "account_id": 2, "status": "active", "closed_at": null,
  "created_at": "2026-01-01T10:00:00Z",
  "current_amount": "3250.00", "deposited": "3250.00",
  "remaining": "6750.00", "percent": 32.5, "is_reached": false,
  "by_account": [ { "account_id": 2, "account_name": "Savings", "amount": "3250.00" } ],
  "days_saving": 241, "days_to_plan": 125, "days_taken": null
}
```

## Assets & Net Worth

Assets are manually tracked, non-cash capital — property, a car, things, anything whose worth you
want counted. Cash is **not** an asset; it's derived automatically from account balances and shows up
in the net worth summary alongside assets, not as an `Asset` row.

Each asset has a value **history** (`AssetValuation` rows, one per date) rather than a single
number — creating an asset seeds its first valuation, and you add more over time to track
appreciation and depreciation.

**`AssetClass`:** `investments` · `crypto` · `real_estate` · `vehicles` · `precious_metals` · `other`
**`CapitalRole`** (how it behaves month to month — user-tagged, not inferred): `income` (e.g. a
rented-out flat) · `neutral` (e.g. a laptop used for work) · `drain` (e.g. a car that wants servicing
and insurance)
**`RiskLevel`** (risk of loss — user-tagged): `low` · `medium` · `high`

| Method | Path | Description |
|---|---|---|
| `GET` | `/assets` | List assets, each with its current (latest) value. |
| `POST` | `/assets` | Create an asset, seeding its first valuation. |
| `PATCH` | `/assets/{id}` | Update asset metadata (not its value — use the valuations endpoints). |
| `DELETE` | `/assets/{id}` | Delete an asset and its whole valuation history. |
| `GET` | `/assets/{id}/valuations` | Full value history, oldest first. |
| `POST` | `/assets/{id}/valuations` | Record a value as of a date. Re-posting the same date **updates** that day's value (upsert) instead of erroring. |
| `PATCH` | `/assets/{id}/valuations/{valuation_id}` | Correct a recorded valuation — its `value`, its `as_of_date`, or both. `409` if that date already has one. |
| `DELETE` | `/assets/{id}/valuations/{valuation_id}` | Remove one valuation. |
| `GET` | `/net-worth/summary` | Aggregated capital: timeline, breakdown by class, by capital role, by risk level. |

**Create asset body:**

```json
{
  "name": "Flat",
  "asset_class": "real_estate",
  "currency": null,
  "notes": null,
  "capital_role": "neutral",
  "monthly_cash_flow": null,
  "risk_level": "low",
  "is_personal_use": true,
  "value": 10000000,
  "as_of_date": "2026-08-29"
}
```

- `currency`: omit it and the install's currency is used.
- `is_personal_use`: the home you live in, the car you drive. It counts towards capital but not
  towards liquid money — which is the whole point of the flag. Without it, somebody who saved five
  million and bought a car would appear to have lost everything.

**Add valuation:** `{"value": 9500000, "as_of_date": "2026-08-30"}`. **Correct one:** the same two
fields, both optional. Moving a valuation onto a day that already has one is refused with `409`
rather than silently overwriting the other: two prices for one day aren't a second valuation, they're
a lost first one.

**`GET /net-worth/summary`** — `?range=` one of `30d`, `90d`, `1y`, `5y`, `all`, or `custom` with
`?start_date=&end_date=` (default `30d`). `?currency=` picks which currency to look at.

**Capital is computed per currency and never converted.** A rouble view shows rouble accounts and
rouble assets, a dollar view shows dollar ones; `other_base` and `total_base` say what the rest comes
to in the install's currency, so nothing is hidden, but the headline figure is never a sum of
different money.

```json
{
  "range": "30d",
  "currency": "RUB",
  "currencies": ["RUB", "USD"],
  "current": "48250.00",
  "other_base": "1500.00",
  "total_base": "49750.00",
  "liquid": "5250.00",
  "personal_use": "10000000.00",
  "liabilities": "81614.10",
  "change_amount": "1200.00",
  "change_percent": 2.55,
  "series": [ { "date": "2026-08-01", "value": "47050.00" } ],
  "breakdown": [
    { "key": "cash", "name": "Cash", "color": "#…", "icon": "wallet", "amount": "5250.00", "percent": 10.88 }
  ],
  "capital_roles": [
    { "role": "income", "label": "Income", "color": "#…", "total_value": "25000.00", "monthly_cash_flow": "0.00", "count": 1 }
  ],
  "risk_levels": [
    {
      "risk_level": "low", "label": "Low", "color": "#…",
      "total_value": "5250.00", "percent": 10.88,
      "items": [ { "key": "cash", "name": "Cash", "amount": "5250.00", "percent": 100.0 } ]
    }
  ]
}
```

The `series` never starts earlier than the first record you actually have: a flat zero line before
that is a claim the data doesn't support.

## Investments

Stocks, bonds, funds and metals, held in portfolios, with a trade log per holding. Position size and
cost are **derived** from the trades, never sent directly.

**Disposals use FIFO** — the oldest lot is sold first. That's how a broker's report and the tax
authority compute it, so the figures here match the broker's app; average cost would quietly
understate a loss.

**`InvestmentKind`:** `stock` · `bond` · `fund`, and the rest of the list in `models/enums.py`.
**`TradeSide`:** `buy` · `sell`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/investments/portfolios` | Portfolios with holding count, value and cost basis. `?include_archived=true`. |
| `POST` | `/investments/portfolios` | Create a portfolio: `{"name", "color"}`. |
| `PATCH` | `/investments/portfolios/{id}` | Update (partial), `is_archived` included. |
| `DELETE` | `/investments/portfolios/{id}` | Delete a portfolio. |
| `GET` | `/investments/holdings` | Holdings with quantity, average cost, value, realised and unrealised P&L. `?portfolio_id=`. |
| `GET` | `/investments/holdings/{id}` | One holding plus `open_lots` (what's still held, at what cost) and `disposals` (which lots each sale consumed). |
| `POST` | `/investments/holdings` | Create a holding inside a portfolio. |
| `PATCH` | `/investments/holdings/{id}` | Update (partial). This is where `last_price` is set: there is no price feed for securities. |
| `DELETE` | `/investments/holdings/{id}` | Delete a holding and its trades. |
| `GET` | `/investments/holdings/{id}/trades` | The trade log for one holding. |
| `POST` | `/investments/holdings/{id}/trades` | Add a trade. |
| `PATCH` | `/investments/trades/{id}` | Correct one trade; everything downstream is recomputed. |
| `DELETE` | `/investments/trades/{id}` | Remove one trade; same recomputation. |

**Trade body:** `{"side": "buy", "quantity": 10, "price_per_unit": 250.40, "fee": 1.50,
"trade_date": "2026-08-29", "account_id": 1, "note": null}`.

`oversold` on a holding is the quantity sold beyond what the log says was ever bought — it isn't
silently clamped to zero, because the honest answer to an inconsistent log is to show the
inconsistency.

## Crypto

Live-priced crypto holdings with a full buy/sell history, kept current against
[CoinGecko](https://www.coingecko.com/en/api/pricing)'s Demo API. Under the hood each holding **is**
an Asset (`asset_class=crypto`, see [Assets & Net Worth](#assets--net-worth)) — deleting one is
`DELETE /assets/{asset_id}`, not a separate endpoint, and it shows up in `/net-worth/summary` like any
other asset automatically.

**Quantity and average buy price are never sent directly — they're derived** from the log of buy/sell
transactions, using the weighted-average-cost method: a buy blends into the running average cost; a
sell reduces quantity but leaves the average cost of what's still held unchanged. (Securities use
FIFO instead — a broker's report does, and these figures have nobody to match.)

Requires `AURUM_COINGECKO_API_KEY` in `.env` (a free Demo key, no card required). Endpoints that need
CoinGecko (`/crypto/holdings` on creation, `/crypto/refresh`, `/crypto/search`) return `400` with a
message telling you so if it's unset — adding a transaction to an existing holding never needs it at
all.

Prices are **never** fetched in the background — there's no scheduler in this stack. Two triggers
only: `POST /crypto/refresh` (a manual "refresh now"), and a lazy check on every `GET
/crypto/holdings` that only actually calls CoinGecko once 24h have passed since the last successful
sync. If CoinGecko is unreachable, existing values are left untouched and `error_key` is set instead
of the whole request failing.

| Method | Path | Description |
|---|---|---|
| `GET` | `/crypto/portfolios` | Portfolios, for grouping holdings. `?include_archived=true`. |
| `POST` | `/crypto/portfolios` | Create one: `{"name"}`. |
| `PATCH` | `/crypto/portfolios/{id}` | Rename it, or set `is_archived`. |
| `DELETE` | `/crypto/portfolios/{id}` | Delete it; the holdings themselves stay. |
| `GET` | `/crypto/holdings` | Holdings with live price and computed quantity/avg buy price/P&L. `?portfolio_id=`. Also runs the lazy once-a-day auto-refresh. |
| `POST` | `/crypto/refresh` | Force a price refresh right now, bypassing the 24h window. `?portfolio_id=`. |
| `POST` | `/crypto/holdings` | Add a new holding — its first buy transaction, inline. Fetches today's price immediately so it isn't `null` until the next sync. |
| `GET` | `/crypto/holdings/{asset_id}/transactions` | Full buy/sell history for one holding, newest first. |
| `POST` | `/crypto/holdings/{asset_id}/transactions` | Buy more of, or sell some of, a coin already tracked. Never calls CoinGecko. `400` if a sell would exceed what's currently held. |
| `PATCH` | `/crypto/transactions/{id}` | Edit one transaction (partial). `400` if the change would oversell. |
| `DELETE` | `/crypto/transactions/{id}` | Remove one transaction; quantity/avg buy price/value are recomputed from what's left. |
| `GET` | `/crypto/search` | `?q=` — search CoinGecko for a coin to add (name/ticker, returns its `coingecko_id` + logo). |
| `GET` | `/crypto/history` | `?range=7d\|30d\|90d\|all` (default `30d`) — total crypto value over time. No `24h`: the resolution is only as dense as the sync cadence above. |
| `GET` | `/crypto/performance/90d` | 90-day price change per holding, as a percentage. `?portfolio_id=`. |

**Create body** (`POST /crypto/holdings`):

```json
{
  "portfolio_id": 1,
  "coingecko_id": "bitcoin",
  "symbol": "btc",
  "name": "Bitcoin",
  "thumb_url": "https://…",
  "quantity": "0.05",
  "price_per_unit": "55000",
  "date": "2026-08-01",
  "note": null
}
```

`coingecko_id` is CoinGecko's own stable id (not the ticker — tickers collide across unrelated
coins) — get it from `/crypto/search` rather than guessing. `quantity`/`price_per_unit` support up to
18 decimal places (wei-level token amounts). `price_per_unit` is what you actually paid, in the app's
display currency — it's stored as-is, never re-derived from market data later.

**Add a transaction:** `{"type": "sell", "quantity": "0.02", "price_per_unit": "61000",
"date": "2026-08-30", "note": null}`. `type` is `"buy"` or `"sell"`.

**`GET /crypto/holdings` / `POST /crypto/refresh` response:**

```json
{
  "synced": true,
  "last_synced_at": "2026-08-30T12:00:00Z",
  "error_key": null,
  "source_configured": true,
  "holdings": [
    {
      "asset_id": 7, "portfolio_id": 1,
      "coingecko_id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "thumb_url": "https://…",
      "quantity": "0.05", "avg_buy_price": "55000.00", "current_price": "61000.00",
      "value": "3050.00", "cost_basis": "2750.00",
      "profit_loss": "300.00", "profit_loss_percent": 10.91
    }
  ]
}
```

`current_price`/`value` are `null` only for a holding whose very first price fetch failed (CoinGecko
was down right when it was added) — distinct from a real `0`. `avg_buy_price`/`cost_basis`/
`profit_loss`/`profit_loss_percent` are `null` once a holding's quantity has been fully sold down to
zero (nothing left to have a cost basis). `error_key` is `"unreachable"` when a sync attempt couldn't
reach CoinGecko (existing values are kept as-is), or `null` otherwise.

**`GET /crypto/history` response:**

```json
{
  "range": "30d",
  "current": "9727.68",
  "change_amount": "1240.16",
  "change_percent": 14.6,
  "series": [ { "date": "2026-08-01", "value": "8487.52" } ]
}
```

One point per calendar day, forward-filled from whatever `AssetValuation` snapshots actually exist
(same technique as `/net-worth/summary`'s own `series`, just scoped to crypto-class assets) — a day
with no sync simply repeats the last known total rather than leaving a gap.

## Dashboard, Cash Flow & Reports

Read-only aggregation endpoints — the numbers behind the charts. Useful for pulling summary data into
an external dashboard without recomputing it yourself.

| Method | Path | Description |
|---|---|---|
| `GET` | `/dashboard/summary` | Headline numbers for a period. `?year=&month=&range=month\|year\|all` (default: this month). |
| `GET` | `/cash-flow` | Income against expense, month by month, opening balances included. `?start_date=&end_date=` (default: all history). |
| `GET` | `/reports/category-spending` | One category's spend over time. `?category_id=` (required) `&start_date=&end_date=`. |
| `GET` | `/reports/category-ranking` | Categories ranked by total over a period. `?kind=expense\|income` (default `expense`) `&start_date=&end_date=`. |

**`GET /dashboard/summary` response:**

```json
{
  "year": 2026, "month": 8, "start_date": "2026-08-01", "end_date": "2026-08-31",
  "real_income": "5200.00",
  "spent": "3120.45",
  "to_people": "400.00",
  "lent_net": "150.00",
  "net": "2079.55",
  "transferred_out": "500.00",
  "hours_worked": "160.00",
  "earned_per_hour": "32.50",
  "spending_by_category": [
    { "category_id": 4, "name": "Groceries", "color": "#22c55e", "icon": "shopping-cart",
      "amount": "612.30", "percent": 19.6, "children": [] }
  ],
  "income_by_category": [],
  "accounts": [
    { "account_id": 1, "name": "Checking", "balance": "1523.40", "currency": "USD",
      "balance_base": "1523.40", "reserved": "300.00", "available": "1223.40", "nature": "asset" }
  ],
  "largest_expenses": [],
  "monthly": [ { "year": 2026, "month": 7, "income": "5200.00", "expense": "3400.00", "net": "1800.00" } ],
  "daily": [ { "date": "2026-08-01", "income": "0.00", "expense": "42.50", "net": "-42.50" } ]
}
```

- `real_income` is earnings only: money received from people is never income, whichever
  `settlement_kind` it carried.
- `spent` includes what was given to people for good, and what was lent when
  `lending_is_spending` is on. `to_people` is how much of `spent` went to people rather than into
  purchases; `lent_net` is lending minus repayments received, reported either way so the gap between
  the period's result and the money that actually moved is always named on screen.
- `accounts` balances are **as of today** and don't depend on the period: "how much do I have right
  now" has nothing to do with which months you're looking at.
- `daily` is only filled in when `range=month` — a day-resolution series over five years is a chart
  nobody can read.

**`GET /cash-flow` response:**

```json
{
  "start_date": null, "end_date": null,
  "points": [ { "year": 2026, "month": 7, "income": "5200.00", "expense": "3400.00",
                "net": "1800.00", "opening": "0.00" } ],
  "total_income": "62400.00", "total_expense": "40800.00",
  "total_net": "21600.00", "total_opening": "7354.71"
}
```

Transfers between your own accounts are excluded — they are neither income nor expense. Accounts'
opening balances **are** included: they were earned too, just before the ledger starts, and without
them the result doesn't match what's on the cards.

## Insights & Advice

Rules-based, computed on read — no ML, no background jobs. Both read from the same transaction /
account / asset data as everything else; thresholds are configurable via [Settings](#settings).

| Method | Path | Description |
|---|---|---|
| `GET` | `/insights/alerts` | Active alerts (negative cash flow streak, declining capital, over-budget category, risky allocation, idle cash). |
| `GET` | `/advice` | Plain-language observations (rising spending categories, unbudgeted top expenses, savings-rate trend). |

Both return a `key` + machine-readable `params` per item rather than pre-rendered text — the
frontend interpolates a localized message client-side, so build your own message from `key`/`params`
if you're consuming this programmatically rather than trying to parse rendered strings.

```json
// GET /insights/alerts
{ "alerts": [ { "key": "idle_cash", "severity": "warning", "params": { "account_id": 2, "days": 75 } } ] }

// GET /advice
{ "items": [ { "key": "rising_category", "tone": "warning", "params": { "category": "Dining", "percent": 34.2 } } ] }
```

## Settings

App-wide configuration: the install's currency, its language, display preferences and every alert
threshold. Single row, created automatically on first run — there's nothing to create, only to
read/update.

| Method | Path | Description |
|---|---|---|
| `GET` | `/settings` | Read current settings. |
| `PATCH` | `/settings` | Update settings (partial). |

```json
{
  "currency": "RUB",
  "language": "ru",
  "negative_cash_flow_threshold_months": 2,
  "net_worth_decline_threshold_months": 2,
  "risky_allocation_threshold_percent": 20,
  "idle_cash_threshold_amount": "1000.00",
  "idle_cash_threshold_days": 60,
  "default_dashboard_range": "year",
  "default_account_id": null,
  "show_cents": true,
  "lending_is_spending": true,
  "default_page_size": 50,
  "group_repeats_by_default": true,
  "day_dividers_by_default": true
}
```

- `currency`: 3-letter uppercase code — the currency totals are computed in. Not a display label:
  every transaction's `amount_base` is converted into it.
- `language`: `ru` or `en`.
- `negative_cash_flow_threshold_months` / `net_worth_decline_threshold_months`: consecutive months
  before the corresponding alert fires (`1`–`24`).
- `risky_allocation_threshold_percent`: max % of total capital allowed in medium/high risk tiers
  before `risky_allocation_exceeded` fires (`1`–`100`).
- `idle_cash_threshold_amount` / `idle_cash_threshold_days`: balance + days of no activity a
  depository account needs to hit before `idle_cash` fires.
- `default_dashboard_range`: which period the dashboard opens on — `month`, `year` or `all`.
- `default_account_id`: preselected account in the new-transaction form.
- `show_cents`: show exact figures rather than rounded ones. The savings rate follows it too.
- **`lending_is_spending`:** whether money lent to a person counts as spending. There is no right
  answer, and that is exactly why it's a setting: the money left the account, so it's spending; it
  will come back, so it isn't. Both answers are honest and the choice belongs to whoever owns the
  money. On (the default), the period's result matches the money, and a month in which more left the
  accounts than came in doesn't look like saving. Off, lending leaves the expense figure and
  `lent_net` says where it went instead — the gap is named either way, never left a mystery.
- `default_page_size` (`10`–`500`), `group_repeats_by_default`, `day_dividers_by_default`: list
  display defaults.

## Spreadsheet Import

A one-shot migration for a hand-made ledger kept in Google Sheets or Excel: it brings over
categories, accounts, participants, plans and the whole history at once. The format and how to adapt
the parser to your own sheet are in [docs/spreadsheet-import.md](docs/spreadsheet-import.md).

| Method | Path | Description |
|---|---|---|
| `POST` | `/import/spreadsheet/preview` | Parse and report what *would* happen. Writes nothing. |
| `POST` | `/import/spreadsheet/apply` | Write everything, in one database transaction. |

Both take `multipart/form-data` with a `transactions` file (the operations sheet as UTF-8 CSV) and an
optional `settings` file:

```bash
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/import/spreadsheet/preview \
  -F "transactions=@operations.csv"
```

The preview counts incomes, expenses, transfers, goal contributions and excluded rows, lists the
accounts and opening balances it would create, and returns an `issues` array for every row it
couldn't make sense of. `can_apply` is `false` when the install already holds transactions:
**the import only runs on an empty ledger**, because a second pass would double the history and no
one could later tell which of two identical bus rides was the spare.

Apply is all-or-nothing. Half a history is worse than none — you can't tell from it what's missing.

## Backup & Restore

A full snapshot of every table as one JSON document — the same mechanism the in-app Settings →
Backup & Restore uses. Good for scripted off-site backups, or for migrating data programmatically.

| Method | Path | Description |
|---|---|---|
| `GET` | `/backup/export` | Download a full backup as JSON. |
| `POST` | `/backup/import` | Restore from a backup file — **replaces existing data**, all-or-nothing. |

```bash
# Export
curl -b /tmp/aurum.jar http://localhost:3000/api/backup/export -o aurum-ex-backup.json

# Restore
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/backup/import \
  -H "Content-Type: application/json" \
  -d @aurum-ex-backup.json
```

The payload includes an `aurum_backup_version` field checked on import — a file from an incompatible
future format is rejected outright rather than partially applied. Every table is covered, and a test
counts every row before export and after restore to keep that true. Treat `/backup/import` as
destructive: back up your current data first if you're experimenting.

## Recipes

Every recipe assumes you've signed in once and kept the cookie jar:

```bash
curl -c /tmp/aurum.jar -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'
```

### Add an expense transaction

```bash
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "category_id": 4,
    "type": "expense",
    "amount": 12.50,
    "description": "Coffee",
    "date": "2026-08-30"
  }'
```

### Add income with a tag

```bash
# 1. Find or create the tag
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/tags \
  -H "Content-Type: application/json" -d '{"name": "Freelance"}'
# -> {"id": 9, "name": "Freelance"}

# 2. Create the transaction referencing it
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "category_id": 2,
    "type": "income",
    "amount": 800,
    "description": "Client invoice",
    "date": "2026-08-30",
    "tag_ids": [9]
  }'
```

### Move money between two of your own accounts

```bash
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "transfer_account_id": 2,
    "type": "transfer",
    "amount": 500,
    "description": "Move to savings",
    "date": "2026-08-30"
  }'
```

### Record lending money to a friend

```bash
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "type": "external_out",
    "settlement_kind": "loan_out",
    "counterparty_id": 4,
    "amount": 1000,
    "description": "Until payday",
    "date": "2026-08-30"
  }'
```

The repayment is the same call with `"type": "external_in"` and `"settlement_kind": "repayment"`.
Neither touches income; `GET /settlements` shows the balance between you.

### Record a receipt with line items

```bash
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "category_id": 4,
    "type": "expense",
    "amount": 145.40,
    "description": "Grocery run",
    "store_id": 5,
    "date": "2026-08-30",
    "items": [
      { "product_id": 8, "name": "Milk", "quantity": 1, "unit_id": 3, "price": 89.90, "amount": 89.90 },
      { "product_id": 9, "name": "Bread", "quantity": 1, "unit_id": 4, "price": 55.50, "amount": 55.50 }
    ]
  }'
```

### Pull this month's spend by category (for an external dashboard)

```bash
curl -b /tmp/aurum.jar "http://localhost:3000/api/dashboard/summary?range=month" \
  | jq '.spending_by_category'
```

### Bulk-import transactions from your own data source

```bash
curl -b /tmp/aurum.jar -X POST http://localhost:3000/api/transactions/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "account_id": 1, "type": "expense", "amount": 9.99, "description": "Subscription", "date": "2026-08-01" },
      { "account_id": 1, "type": "expense", "amount": 45.00, "description": "Fuel", "date": "2026-08-03" }
    ]
  }'
```

---

For self-hosting, environment variables, and running Aurum-Ex itself, see [README.md](README.md).
What each screen is for is explained in [docs/guide.md](docs/guide.md).
