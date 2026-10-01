"""Net worth aggregation: a single trend line plus a percent breakdown by
asset class.

Design note: "Cash" is not stored anywhere — it's derived live from
Account/Transaction data (checking/savings/cash/investment accounts) so the
Transactions feature stays the single source of truth for liquid money.
Investment accounts count here too: their balance is uninvested/unallocated
money sitting on the account, not the market value of what's actually
invested — that value is still tracked manually via Asset/AssetValuation,
same as every other class (investments, crypto, real estate, vehicles,
precious metals, other). Without this, money deposited into an investment
account but not yet turned into a valued Asset silently disappeared from
net worth. Both halves are collapsed into one
daily, forward-filled series so the chart reads as one continuous line even
though the two halves are updated at very different cadences.
"""
from collections import defaultdict
from datetime import date as date_
from datetime import timedelta
from decimal import Decimal
from itertools import groupby

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.enums import (
    AccountKind,
    AccountNature,
    AssetClass,
    CapitalRole,
    RiskLevel,
    TransactionType,
)
from app.models.transaction import Transaction
from app.services.account_service import get_balances_by_account
from app.services.currency_service import (
    convert_balance,
    get_base_currency,
    get_current_rates,
)
from app.schemas.net_worth import (
    CapitalRoleSummary,
    NetWorthBreakdownItem,
    NetWorthPoint,
    NetWorthSummary,
    RiskLevelItem,
    RiskLevelSummary,
)

CASH_ACCOUNT_TYPES = {AccountKind.CHECKING, AccountKind.SAVINGS, AccountKind.CASH, AccountKind.INVESTMENT}

RANGE_DAYS = {"30d": 30, "90d": 90, "1y": 365, "5y": 365 * 5}

_CLASS_META: dict[str, tuple[str, str, str]] = {
    # key -> (display name, color, lucide icon). Colors follow the dataviz
    # skill's validated 8-slot order (blue, orange, aqua, yellow, magenta,
    # green, violet, red) in this exact sequence — an adjacent-pair-safe
    # order for a segmented bar/donut; do not reorder without re-validating.
    # Деньги делятся надвое, и это не придирка к словам. Купюра в кармане
    # — это деньги; остаток на карте — обязательство банка выплатить их по
    # требованию. Риски у них разные: банк может ограничить доступ, а
    # карман нет. Называть вторую строку «наличными» значит стирать
    # различие, которое как раз и стоит держать на виду.
    #
    # Третьей строки под цифровые деньги нет намеренно: цифровой рубль
    # хранится не на банковском счёте, и когда он появится у кого-то из
    # пользователей, ему понадобится свой вид счёта, а не переименование
    # этой строки. Криптовалюта своя строка уже есть.
    "cash": ("Наличные", "#2a78d6", "wallet"),  # slot 1 blue
    "bank": ("На счетах", "#4a9de0", "landmark"),  # slot 1, светлее
    AssetClass.INVESTMENTS.value: ("Инвестиции", "#eb6834", "trending-up"),  # slot 2 orange
    AssetClass.CRYPTO.value: ("Криптовалюта", "#1baf7a", "bitcoin"),  # slot 3 aqua
    AssetClass.REAL_ESTATE.value: ("Недвижимость", "#eda100", "building-2"),  # slot 4 yellow
    AssetClass.VEHICLES.value: ("Транспорт", "#e87ba4", "car"),  # slot 5 magenta
    AssetClass.PRECIOUS_METALS.value: ("Драгметаллы", "#008300", "gem"),  # slot 6 green
    AssetClass.OTHER.value: ("Прочее", "#4a3aa7", "package"),  # slot 7 violet
}

_ROLE_META: dict[CapitalRole, tuple[str, str]] = {
    # role -> (label, color). Status colors, not categorical ones — "good"
    # and "critical" from the dataviz skill's fixed status palette, reused
    # verbatim from how StatCard/NetWorthChart already color income vs.
    # expense elsewhere in the app.
    CapitalRole.INCOME: ("Доходный", "var(--success)"),
    CapitalRole.NEUTRAL: ("Нейтральный", "var(--text-muted)"),
    CapitalRole.DRAIN: ("Убыточный", "var(--danger)"),
}

_RISK_META: dict[RiskLevel, tuple[str, str]] = {
    # Same status-color reuse as _ROLE_META — low risk reads as "good",
    # high risk as "critical", not a categorical hue.
    RiskLevel.LOW: ("Низкий", "var(--success)"),
    RiskLevel.MEDIUM: ("Средний", "var(--text-muted)"),
    RiskLevel.HIGH: ("Высокий", "var(--danger)"),
}


def _daily_series(events: list[tuple[date_, Decimal]], start: date_, end: date_) -> list[NetWorthPoint]:
    """Forward-fills a sparse, date-sorted list of cumulative totals into one
    point per calendar day. `events` before `start` still count — they just
    collapse into `start`'s opening value."""
    events = sorted(events, key=lambda e: e[0])
    points: list[NetWorthPoint] = []
    idx, n = 0, len(events)
    current = Decimal("0")
    day = start
    while day <= end:
        while idx < n and events[idx][0] <= day:
            current = events[idx][1]
            idx += 1
        points.append(NetWorthPoint(date=day, value=current))
        day += timedelta(days=1)
    return points


def _counted_account(
    kind: AccountKind,
    nature: AccountNature,
    kinds: set[AccountKind] | None,
    debt_only: bool,
) -> bool:
    """Входит ли счёт в денежный ряд.

    По умолчанию — деньги за вычетом долгов: денежные счета плюс все счета
    с природой «обязательство». Минус на кредитке и есть долг, и остаток
    такого счёта отрицателен сам по себе — прибавить его значит вычесть
    долг.

    Раньше отбор шёл по одному виду счёта, и кредитной карты в нём не было
    вовсе. Капитал и «быстрые деньги» показывали сумму положительных счетов,
    а долг по картам не вычитался никогда: 127 тысяч там, где на самом деле
    72. Хотя в описании «быстрых денег» с самого начала было сказано «за
    вычетом долга по картам».

    `kinds` — срез внутри положительных денег (например, одни наличные):
    долгов в нём нет по определению. `debt_only` — сам долг, отдельно.
    """
    if debt_only:
        return nature is AccountNature.LIABILITY
    if kinds is not None:
        return kind in kinds and nature is not AccountNature.LIABILITY
    return nature is AccountNature.LIABILITY or kind in CASH_ACCOUNT_TYPES


async def _cash_cumulative_events(
    session: AsyncSession,
    currency: str,
    kinds: set[AccountKind] | None = None,
    *,
    debt_only: bool = False,
) -> list[tuple[date_, Decimal]]:
    """Накопительный итог по денежным счетам, день за днём.

    Три поправки против исходной версии, и каждая иначе искажала капитал:

      * **начальный остаток счёта** входит в расчёт. Без него деньги,
        лежавшие на счёте до первой операции, просто пропадали, и график
        начинался с отрицательного значения там, где на счёте были деньги;
      * **записи «не учитывать» пропускаются.** Возвращённый товар остаётся
        в истории, но денег не двигает — иначе возврат навсегда вычитался
        из капитала;
      * **EXTERNAL_IN / EXTERNAL_OUT** двигают баланс наравне с доходом и
        расходом: они не заработок, но деньги на счёте от этого меняются.

    `kinds` сужает набор счетов — так считается доля наличных внутри
    денежного итога. Тем же расчётом, а не отдельной формулой: две разные
    формулы для целого и его части рано или поздно разойдутся, и в сумме
    перестанет получаться целое.

    `currency` сужает его же по валюте, и это главное здесь изменение.
    Кривая рисуется в одной валюте и ничего не переводит: сто евро на
    евровой карте — это сто евро, а не их сегодняшняя цена в рублях и не
    вчерашняя. Капитал — состояние, а не событие, и переводить его значило
    бы каждый день заново переписывать всю историю графика курсом дня.

    Отсюда и суммы: берётся собственная сумма операции, а не приведённая к
    валюте установки. В пределах одной валюты это одно и то же число, но
    брать приведённое было бы неверно по смыслу — и сразу неверно по
    величине, если валюта счёта не совпадает с валютой установки.
    """
    target = currency.upper()
    accounts_result = await session.execute(
        select(Account.id, Account.kind, Account.nature, Account.opening_balance, Account.currency)
    )
    cash_accounts = {
        acc_id: opening or Decimal("0")
        for acc_id, acc_kind, acc_nature, opening, acc_currency in accounts_result.all()
        if _counted_account(acc_kind, acc_nature, kinds, debt_only)
        and (acc_currency or "").upper() == target
    }
    cash_account_ids = set(cash_accounts)

    txns_result = await session.execute(
        select(
            Transaction.date,
            Transaction.type,
            # Своя сумма операции, не приведённая: см. про валюту выше.
            Transaction.amount,
            Transaction.account_id,
            Transaction.transfer_account_id,
            Transaction.is_excluded,
            # Сколько пришло на счёт получателя, в его валюте. Перевод
            # между валютами уходит с одной кривой и приходит на другую —
            # каждая видит свою сторону, и разницу между ними (курс банка и
            # его комиссию) видно как расхождение двух кривых.
            Transaction.transfer_amount,
        )
    )

    delta_by_date: dict[date_, Decimal] = defaultdict(Decimal)
    for (
        tx_date,
        tx_type,
        amount,
        account_id,
        transfer_account_id,
        is_excluded,
        transfer_amount,
    ) in txns_result.all():
        if is_excluded:
            continue
        # Операция без курса на свою дату в итог не входит: раньше на её
        # месте стояла единица, и валютная покупка попадала в капитал своей
        # цифрой, как будто она в рублях.
        if amount is None:
            continue
        if tx_type in (TransactionType.INCOME, TransactionType.EXTERNAL_IN) and account_id in cash_account_ids:
            delta_by_date[tx_date] += amount
        elif tx_type in (TransactionType.EXPENSE, TransactionType.EXTERNAL_OUT) and account_id in cash_account_ids:
            delta_by_date[tx_date] -= amount
        elif tx_type == TransactionType.TRANSFER:
            if account_id in cash_account_ids:
                delta_by_date[tx_date] -= amount
            if transfer_account_id in cash_account_ids:
                delta_by_date[tx_date] += (
                    transfer_amount if transfer_amount is not None else amount
                )

    # Начальные остатки — стартовая точка ряда: они были на счетах ещё до
    # первой записи.
    events: list[tuple[date_, Decimal]] = []
    running = sum(cash_accounts.values(), Decimal("0"))
    for day in sorted(delta_by_date):
        running += delta_by_date[day]
        events.append((day, running))
    return events


async def _asset_events_and_class_totals(
    session: AsyncSession, currency: str
) -> tuple[list[tuple[date_, Decimal]], dict[AssetClass, Decimal], dict[int, Decimal]]:
    """Оценки имущества, день за днём, в одной валюте.

    Отбор по валюте — по той же причине, что и у счетов: квартира,
    оценённая в долларах, стоит столько долларов, а не их сегодняшнюю цену
    в рублях. Раньше оценки складывались как голые числа независимо от
    валюты, и доллары попадали в рублёвый итог единица за единицу.
    """
    target = currency.upper()
    asset_rows = (
        await session.execute(select(Asset.id, Asset.asset_class, Asset.currency))
    ).all()
    asset_class_map = {
        asset_id: asset_class
        for asset_id, asset_class, asset_currency in asset_rows
        if (asset_currency or "").upper() == target
    }

    valuations_result = await session.execute(
        select(AssetValuation.asset_id, AssetValuation.as_of_date, AssetValuation.value)
        .where(AssetValuation.asset_id.in_(asset_class_map.keys()))
        .order_by(AssetValuation.as_of_date)
    )
    rows = valuations_result.all()

    current_by_asset: dict[int, Decimal] = {}
    events: list[tuple[date_, Decimal]] = []
    for day, group in groupby(rows, key=lambda row: row[1]):
        for asset_id, _, value in group:
            current_by_asset[asset_id] = value
        events.append((day, sum(current_by_asset.values(), Decimal("0"))))

    class_totals: dict[AssetClass, Decimal] = defaultdict(Decimal)
    for asset_id, value in current_by_asset.items():
        asset_class = asset_class_map.get(asset_id)
        if asset_class is not None:
            class_totals[asset_class] += value

    return events, class_totals, current_by_asset


async def _capital_role_summary(
    session: AsyncSession,
    current_by_asset: dict[int, Decimal],
    cash_total: Decimal,
    currency: str,
) -> list[CapitalRoleSummary]:
    """Cross-cuts the same assets by how the user tagged them (income /
    neutral / drain) instead of by asset class — always all three roles,
    even at zero, so the block reads as a fixed scale rather than a list
    that shuffles as assets are added.

    Деньги на счетах попадают сюда как NEUTRAL — по той же причине, по
    которой в разрезе риска они отнесены к нулевому уровню: они не приносят
    дохода и ничего не съедают, просто лежат. Без них разрез оставался
    пустым у любого, кто пока не завёл ни одного актива, а доли не
    сходились с капиталом — и человек видел «капитал 55 214», а под ним
    три нуля."""
    # Только активы показанной валюты. Капитал считается в одной валюте и
    # ничего не переводит, а разрез брал все: в рублёвом виде долларовая
    # машина давала «1 актив · 0,00 ₽» и «−500,00 ₽/мес» — её содержание в
    # долларах, подписанное рублём.
    roles_result = await session.execute(
        select(Asset.id, Asset.capital_role, Asset.monthly_cash_flow).where(
            func.upper(Asset.currency) == currency.upper()
        )
    )

    totals_value: dict[CapitalRole, Decimal] = defaultdict(Decimal)
    totals_flow: dict[CapitalRole, Decimal] = defaultdict(Decimal)
    counts: dict[CapitalRole, int] = defaultdict(int)
    for asset_id, role, cash_flow in roles_result.all():
        totals_value[role] += current_by_asset.get(asset_id, Decimal("0"))
        totals_flow[role] += cash_flow or Decimal("0")
        counts[role] += 1

    if cash_total:
        totals_value[CapitalRole.NEUTRAL] += cash_total

    return [
        CapitalRoleSummary(
            role=role.value,
            label=_ROLE_META[role][0],
            color=_ROLE_META[role][1],
            total_value=totals_value.get(role, Decimal("0")),
            monthly_cash_flow=totals_flow.get(role, Decimal("0")),
            count=counts.get(role, 0),
        )
        for role in CapitalRole
    ]


async def _risk_level_summary(
    session: AsyncSession,
    current_by_asset: dict[int, Decimal],
    cash_today: Decimal,
    currency: str,
) -> list[RiskLevelSummary]:
    """Cross-cuts Cash + assets by user-tagged risk of loss — unlike
    capital_roles, Cash participates here: it's the zero-risk anchor an
    80/20-style allocation rule ("80% of capital at zero risk, at most 20%
    exposed") is measured against. Always all three tiers, even at zero,
    same reasoning as capital_roles. Each tier's item list *is* its
    diversification view — a tier that's one holding at 100% is
    concentrated, several even-sized holdings aren't, no separate index."""
    # Только активы показанной валюты — по той же причине, что и в
    # разрезе по типу.
    assets_result = await session.execute(
        select(Asset.id, Asset.name, Asset.risk_level).where(
            func.upper(Asset.currency) == currency.upper()
        )
    )
    asset_rows = assets_result.all()

    totals: dict[RiskLevel, Decimal] = defaultdict(Decimal)
    items_by_level: dict[RiskLevel, list[tuple[str, str, Decimal]]] = defaultdict(list)

    if cash_today:
        totals[RiskLevel.LOW] += cash_today
        # В разрезе по риску наличные и деньги на счетах не разделяются:
        # риск у них один и тот же, низкий, и две одинаковые строки
        # подряд ничего бы не добавили. Название общее и точное —
        # «денежные средства» покрывает и купюры, и остаток на карте.
        items_by_level[RiskLevel.LOW].append(("cash", "Денежные средства", cash_today))

    for asset_id, name, risk_level in asset_rows:
        value = current_by_asset.get(asset_id, Decimal("0"))
        if value == 0:
            continue
        totals[risk_level] += value
        items_by_level[risk_level].append((f"asset:{asset_id}", name, value))

    grand_total = sum(totals.values(), Decimal("0"))

    def _share(amount: Decimal, denominator: Decimal) -> float:
        return float(amount / denominator * 100) if denominator else 0.0

    summaries = []
    for level in RiskLevel:
        tier_total = totals.get(level, Decimal("0"))
        items = [
            RiskLevelItem(key=key, name=name, amount=amount, percent=_share(amount, tier_total))
            for key, name, amount in sorted(items_by_level.get(level, []), key=lambda item: item[2], reverse=True)
        ]
        summaries.append(
            RiskLevelSummary(
                risk_level=level.value,
                label=_RISK_META[level][0],
                color=_RISK_META[level][1],
                total_value=tier_total,
                percent=_share(tier_total, grand_total),
                items=items,
            )
        )
    return summaries


def _earliest_event_date(
    cash_events: list[tuple[date_, Decimal]], asset_events: list[tuple[date_, Decimal]]
) -> date_ | None:
    """Дата первой записи в истории — раньше неё капитал не равен нулю, а
    неизвестен. Пусто, когда записей нет вовсе."""
    all_dates = [e[0] for e in cash_events] + [e[0] for e in asset_events]
    return min(all_dates) if all_dates else None


def _resolve_start_date(range_key: str, cash_events: list[tuple[date_, Decimal]], asset_events: list[tuple[date_, Decimal]], today: date_) -> date_:
    """Начало графика для выбранного периода.

    Никогда не раньше первой записи, даже когда просят пять лет, а истории
    два года. Иначе график открывается ровной линией по нулю за годы, когда
    учёта не было, — а это утверждение: «капитал тогда был нулевым». На самом
    деле он был неизвестен, и разница существенная: ровная линия в полграфика
    съедает масштаб у самих данных и рисует рост, которого не было.
    """
    earliest = _earliest_event_date(cash_events, asset_events) or today

    if range_key in RANGE_DAYS:
        requested = today - timedelta(days=RANGE_DAYS[range_key] - 1)
        return max(requested, earliest)

    return earliest


async def _latest_asset_values(session: AsyncSession) -> dict[int, Decimal]:
    """Последняя оценка каждого имущества. Строки отсортированы по дате
    убыванию, поэтому первая встреченная и есть свежая."""
    rows = (
        await session.execute(
            select(AssetValuation.asset_id, AssetValuation.value).order_by(
                AssetValuation.asset_id, AssetValuation.as_of_date.desc()
            )
        )
    ).all()
    latest: dict[int, Decimal] = {}
    for asset_id, value in rows:
        latest.setdefault(asset_id, value)
    return latest


async def _capital_by_currency(session: AsyncSession) -> dict[str, Decimal]:
    """Сколько капитала в каждой валюте — в ней самой, без перевода.

    Нужно ровно для одного: сказать, что лежит вне валюты, которую сейчас
    смотрят. Само число «в других валютах» без перевода не выразить —
    евро и юани нельзя сложить, оставаясь честным, — поэтому переводится
    только оно, по сегодняшнему курсу и с оговоркой «примерно». Главная
    величина остаётся своей и нетронутой.
    """
    totals: dict[str, Decimal] = defaultdict(Decimal)

    balances = await get_balances_by_account(session)
    accounts = (
        await session.execute(select(Account.id, Account.kind, Account.nature, Account.currency))
    ).all()
    for account_id, kind, nature, currency in accounts:
        # Тот же отбор, что и у ряда: долг по карте в чужой валюте — тоже
        # часть «в других валютах», только со знаком минус.
        if _counted_account(kind, nature, None, False):
            totals[(currency or "").upper()] += balances.get(account_id, Decimal("0"))

    latest = await _latest_asset_values(session)
    for asset_id, currency in (await session.execute(select(Asset.id, Asset.currency))).all():
        value = latest.get(asset_id)
        if value is not None:
            totals[(currency or "").upper()] += value

    return dict(totals)


async def get_net_worth_summary(
    session: AsyncSession,
    range_key: str,
    start_date: date_ | None = None,
    end_date: date_ | None = None,
    currency: str | None = None,
) -> NetWorthSummary:
    """Капитал за период, в одной валюте.

    `start_date` и `end_date` перекрывают готовый период, когда человек
    задал свой. Начало всё равно не уходит раньше первой записи: ровная
    линия по нулю до неё — это утверждение, которого данные не
    подтверждают. Конец не уходит позже сегодня: капитал завтрашнего дня
    приложению неизвестен, и рисовать его продолжением сегодняшнего значило
    бы выдать догадку за факт.
    """
    today = date_.today()
    base = (await get_base_currency(session)).upper()
    # Валюта не указана — своя. Смотреть капитал начинают с неё, а
    # переключение на другую отвечает на другой вопрос: «сколько у меня
    # долларов», а не «сколько мои доллары стоят».
    target = (currency or base).upper()

    cash_events = await _cash_cumulative_events(session, target)
    asset_events, class_totals, current_by_asset = await _asset_events_and_class_totals(
        session, target
    )

    # Накопительный ряд уже посчитан, последняя точка — сегодняшние деньги.
    # Считаем её до разрезов: они оба принимают её как долю капитала.
    cash_today = cash_events[-1][1] if cash_events else Decimal("0")
    # Наличные считаются тем же расчётом по подмножеству счетов, а деньги
    # на счетах — остаток. Так две строки в сумме всегда дают денежный
    # итог, даже если где-то в расчёте появится ещё одна поправка.
    physical_events = await _cash_cumulative_events(session, target, kinds={AccountKind.CASH})
    physical_today = physical_events[-1][1] if physical_events else Decimal("0")
    # Долг — отдельным рядом тем же расчётом. cash_today уже за его вычетом;
    # положительные деньги получаются обратным сложением, и так три числа
    # сходятся всегда, а не только пока в расчёте нет новых поправок.
    debt_events = await _cash_cumulative_events(session, target, debt_only=True)
    debt_today = debt_events[-1][1] if debt_events else Decimal("0")
    money_today = cash_today - debt_today
    bank_today = money_today - physical_today
    # Разрезы по роли и по риску — про то, в чём лежит капитал, а долг ни в
    # чём не лежит. Отдавать им чистый итог значило бы получить отрицательную
    # «долю денег» у всякого, кто должен по карте больше, чем держит на счетах.
    capital_roles = await _capital_role_summary(session, current_by_asset, money_today, target)

    end = min(end_date, today) if end_date is not None else today
    if start_date is not None:
        # Тот же зажим к первой записи, что и у готовых периодов, — им
        # занимается _resolve_start_date, и обходить его для своего периода
        # значило бы, что «с 2015 года» рисует пять лет пустоты.
        earliest = _earliest_event_date(cash_events, asset_events)
        start = max(start_date, earliest) if earliest else start_date
    else:
        start = _resolve_start_date(range_key, cash_events, asset_events, end)
    # Перевёрнутый диапазон — не ошибка ввода, а промах на один щелчок в
    # выпадающем списке. Показываем один день вместо пустого графика.
    start = min(start, end)

    cash_series = _daily_series(cash_events, start, end)
    asset_series = _daily_series(asset_events, start, end)
    series = [
        NetWorthPoint(date=c.date, value=c.value + a.value) for c, a in zip(cash_series, asset_series, strict=True)
    ]

    current = series[-1].value if series else Decimal("0")
    start_value = series[0].value if series else Decimal("0")
    change_amount = current - start_value
    # За всё время процент не показывается вовсе. История начинается с нуля
    # или почти с нуля, и рост «с сорока рублей до сорока тысяч» даёт сотню
    # тысяч процентов — число, которое ни о чём не говорит: растёт не
    # капитал, а бессмысленность самой доли. На отрезках — месяц, год, пять
    # лет — точка отсчёта уже настоящая, и процент там осмыслен.
    change_percent = (
        float(change_amount / start_value * 100) if range_key != "all" and start_value else None
    )

    risk_levels = await _risk_level_summary(session, current_by_asset, money_today, target)

    # Проценты разбивки — от того, что есть, а не от капитала за вычетом
    # долгов: разбивка отвечает на «из чего состоит имущество», и доли в ней
    # обязаны складываться в сто, сколько бы ни было должно по картам.
    total = money_today + sum(class_totals.values(), Decimal("0"))

    # Быстрые деньги — это денежный итог: он уже считается по счетам,
    # природа которых учтена (карта с долгом уменьшает его). Вложения и
    # крипта сюда не входят: продать их можно, но не завтра и не по
    # известной цене.
    liquid = cash_today

    # Имущество личного пользования. Отдельным запросом по текущим оценкам:
    # class_totals разложены по классам, а личное пользование — другая ось,
    # и недвижимость бывает как жилой, так и сдаваемой.
    personal_rows = (
        await session.execute(select(Asset.id).where(Asset.is_personal_use.is_(True)))
    ).scalars().all()
    personal_use = sum(
        (current_by_asset.get(asset_id, Decimal("0")) for asset_id in personal_rows),
        Decimal("0"),
    )

    def _percent(amount: Decimal) -> float:
        return float(amount / total * 100) if total else 0.0

    breakdown = []
    # Нулевая строка не показывается: у человека без наличных вообще
    # «Наличные — 0» занимает место и ничего не сообщает.
    for key, amount in (("cash", physical_today), ("bank", bank_today)):
        if amount == 0:
            continue
        name, color, icon = _CLASS_META[key]
        breakdown.append(
            NetWorthBreakdownItem(
                key=key, name=name, color=color, icon=icon, amount=amount, percent=_percent(amount)
            )
        )
    for asset_class in AssetClass:
        name, color, icon = _CLASS_META[asset_class.value]
        amount = class_totals.get(asset_class, Decimal("0"))
        breakdown.append(
            NetWorthBreakdownItem(key=asset_class.value, name=name, color=color, icon=icon, amount=amount, percent=_percent(amount))
        )

    # Что лежит вне выбранной валюты. Переводится только это число и
    # только по сегодняшнему курсу: сложить евро с юанями иначе нельзя, а
    # главную величину перевод не трогает.
    by_currency = await _capital_by_currency(session)
    rates = await get_current_rates(session)
    other_base = sum(
        (
            convert_balance(amount, code, rates)
            for code, amount in by_currency.items()
            if code != target
        ),
        Decimal("0"),
    )
    # Валюты, по которым есть что показать. Своя в списке всегда, даже
    # когда на ней ничего не лежит: переключателю нужно, куда вернуться.
    currencies = sorted({base, target} | {code for code in by_currency if code})

    return NetWorthSummary(
        liabilities=-debt_today,
        range=range_key,
        currency=target,
        currencies=currencies,
        current=current,
        other_base=other_base,
        total_base=convert_balance(current, target, rates) + other_base,
        liquid=liquid,
        personal_use=personal_use,
        change_amount=change_amount,
        change_percent=change_percent,
        series=series,
        breakdown=breakdown,
        capital_roles=capital_roles,
        risk_levels=risk_levels,
    )
