"""Условия по кредитам: ставка, лимит, беспроцентный период.

Сам долг уже описан счётом — баланс уходит в минус, когда занимают, и
возвращается к нулю, когда гасят. Это в исходной таблице было сделано
правильно, и переделывать нечего. Не хватало вокруг: ставки, льготного
периода, минимального платежа. Без них проценты считались раз в месяц
руками, а единственным их следом оставалась категория «Проценты по
кредитам» — 23 931 ₽ против 172 882 ₽ основного долга за два года, то есть
почти четырнадцать процентов сверху, и увидеть это можно было, только
сложив строки задним числом.

Проценты по-прежнему заносятся вручную, и это осознанно. Банк считает их
так, как ни одна формула здесь достоверно не повторит: льготный период,
частичное досрочное погашение, точный счёт дней. Дело приложения —
напомнить и прикинуть, а не делать вид, что оно знает банковское число.
"""
from datetime import date as date_
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.credit import CreditRate, CreditTerms
from app.models.enums import AccountNature
from app.schemas.credit import CreditRateRead, CreditTermsRead, CreditTermsWrite
from app.services.credit_plan_service import minimum_payment_for
from app.services.account_service import get_balances_by_account
from app.services.currency_service import quantize_money

# Год для прикидки процентов. Банки считают по фактическим дням, и 365 против
# 366 даёт расхождение в третьем знаке — для оценки несущественно, а вот
# делать вид, что это точный расчёт, нельзя.
DAYS_IN_YEAR = Decimal("365")


async def _require_liability(session: AsyncSession, account_id: int) -> Account:
    """Условия по кредиту вешаются только на счёт-обязательство.

    Не придирка: ставка на дебетовой карте означала бы, что владелец
    неправильно понял, что такое счёт, и молча принять такую запись значит
    оставить ошибку в данных навсегда.
    """
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.nature != AccountNature.LIABILITY:
        raise HTTPException(
            status_code=400,
            detail="Условия по кредиту можно задать только счёту-обязательству",
        )
    return account


def _build_read(account: Account, terms: CreditTerms, debt: Decimal) -> CreditTermsRead:
    """Собирает ответ, добавляя к условиям то, что из них следует.

    Долг приходит положительным числом: баланс кредитного счёта отрицателен,
    но «должен 12 300» читается человеком легче, чем «баланс −12 300».
    """
    limit = terms.credit_limit
    available = None
    used_percent = None
    if limit is not None and limit > 0:
        # Доступное не опускается ниже нуля: перебор лимита бывает (банк
        # разрешил разовую операцию сверху), но «доступно −500» бессмысленно.
        available = quantize_money(max(limit - debt, Decimal("0")))
        used_percent = float(round(debt / limit * 100, 1))

    monthly_interest = None
    if terms.annual_rate_percent is not None and debt > 0:
        # Прикидка на месяц: долг × ставка / 100 / 365 × 30. Именно прикидка —
        # льготный период здесь не учитывается, потому что приложение не
        # знает, какие покупки в него ещё попадают.
        monthly_interest = quantize_money(
            debt * terms.annual_rate_percent / Decimal("100") / DAYS_IN_YEAR * Decimal("30")
        )

    return CreditTermsRead(
        account_id=account.id,
        account_name=account.name,
        account_currency=account.currency,
        debt=quantize_money(debt),
        annual_rate_percent=terms.annual_rate_percent,
        credit_limit=terms.credit_limit,
        available=available,
        used_percent=used_percent,
        grace_days=terms.grace_days,
        payment_day=terms.payment_day,
        minimum_payment=terms.minimum_payment,
        minimum_payment_percent=terms.minimum_payment_percent,
        # Минимальный платёж от сегодняшнего долга: банк посчитает свой на
        # дату выписки, но порядок суммы человеку нужен раньше.
        minimum_payment_due=minimum_payment_for(
            debt, terms.minimum_payment_percent, terms.minimum_payment
        ),
        rates=[CreditRateRead.model_validate(rate) for rate in terms.rates],
        estimated_monthly_interest=monthly_interest,
        opened_on=terms.opened_on,
        closes_on=terms.closes_on,
        notes=terms.notes,
    )


async def _debt_of(session: AsyncSession, account_id: int) -> Decimal:
    balances = await get_balances_by_account(session)
    # Долг — это отрицательный баланс со снятым знаком. Если кредитный счёт
    # ушёл в плюс (переплатили), долга нет, и это ноль, а не отрицательный
    # долг.
    return max(-balances.get(account_id, Decimal("0")), Decimal("0"))


async def get_credit_terms(session: AsyncSession, account_id: int) -> CreditTermsRead | None:
    account = await _require_liability(session, account_id)
    terms = (
        await session.execute(select(CreditTerms).where(CreditTerms.account_id == account_id))
    ).scalar_one_or_none()
    if terms is None:
        return None
    return _build_read(account, terms, await _debt_of(session, account_id))


async def list_credit_terms(session: AsyncSession) -> list[CreditTermsRead]:
    """Все кредиты разом — для страницы долгов.

    Порядок: сначала самый большой долг. Список отвечает на вопрос «что
    гасить в первую очередь», и самая дорогая строка должна быть сверху.
    """
    rows = (
        await session.execute(
            select(CreditTerms, Account).join(Account, Account.id == CreditTerms.account_id)
        )
    ).all()
    balances = await get_balances_by_account(session)
    result = [
        _build_read(account, terms, max(-balances.get(account.id, Decimal("0")), Decimal("0")))
        for terms, account in rows
    ]
    return sorted(result, key=lambda item: (-item.debt, item.account_name))


async def save_credit_terms(
    session: AsyncSession, account_id: int, payload: CreditTermsWrite
) -> CreditTermsRead:
    """Создаёт или обновляет условия — одна операция вместо POST и PATCH.

    Условия у счёта либо есть, либо нет; промежуточного состояния, которое
    различало бы «создать» и «изменить», не существует, а два эндпоинта
    заставили бы интерфейс сначала выяснять, какой из них звать.
    """
    account = await _require_liability(session, account_id)
    terms = (
        await session.execute(select(CreditTerms).where(CreditTerms.account_id == account_id))
    ).scalar_one_or_none()
    if terms is None:
        terms = CreditTerms(account_id=account_id)
        session.add(terms)
        await session.flush()

    fields = payload.model_dump(exclude_unset=True)
    # Ставки — не колонка, а список строк, и присвоение их сломало бы
    # отношение. Переданный список заменяет матрицу целиком: правка ставки
    # и удаление ставки с точки зрения формы — одно и то же действие
    # «вот как теперь выглядит матрица».
    rates = fields.pop("rates", None)
    for field, value in fields.items():
        setattr(terms, field, value)

    if rates is not None:
        # Старые строки удаляются запросом, новые добавляются по одной.
        # Через коллекцию terms.rates было бы короче, но обращение к
        # незагруженной коллекции в асинхронной сессии — это падение
        # (MissingGreenlet), а загружена она не всегда.
        await session.execute(delete(CreditRate).where(CreditRate.account_id == account_id))
        for order, rate in enumerate(rates):
            session.add(
                CreditRate(
                    account_id=account_id,
                    name=rate["name"].strip(),
                    percent=rate["percent"],
                    condition=(rate.get("condition") or "").strip() or None,
                    sort_order=order,
                )
            )
        await session.flush()

    await session.commit()
    # Сессия живёт с expire_on_commit=False, поэтому после записи в
    # identity map остаётся прежний объект с прежним списком ставок —
    # удалённые строки в ответе выглядели бы живыми. Сброс состояния
    # заставляет следующий запрос прочитать базу заново; обращений к
    # незагруженным коллекциям при этом не происходит, и MissingGreenlet
    # здесь неоткуда взяться.
    session.expire_all()
    terms = (
        await session.execute(select(CreditTerms).where(CreditTerms.account_id == account_id))
    ).scalar_one()
    account = await _require_liability(session, account_id)
    return _build_read(account, terms, await _debt_of(session, account_id))


async def delete_credit_terms(session: AsyncSession, account_id: int) -> None:
    """Убирает условия, но не счёт и не его историю.

    Кредит закрыт — ставка и лимит больше не нужны, а операции по нему
    остаются: это часть того, сколько всё стоило.
    """
    terms = await session.get(CreditTerms, account_id)
    if terms is None:
        raise HTTPException(status_code=404, detail="Credit terms not found")
    await session.delete(terms)
    await session.commit()


async def get_credit_summary(session: AsyncSession) -> dict[str, Decimal]:
    """Итог по кредитам для карточки долгов: сколько должны банкам и во
    сколько это обходится в месяц по текущим ставкам."""
    items = await list_credit_terms(session)
    return {
        "debt": sum((item.debt for item in items), Decimal("0")),
        "estimated_monthly_interest": sum(
            (item.estimated_monthly_interest or Decimal("0") for item in items), Decimal("0")
        ),
    }


def next_payment_date(payment_day: int | None, today: date_) -> date_ | None:
    """Ближайшая дата платежа по числу месяца.

    Тридцать первого числа нет в феврале, и банк в таком случае ждёт платёж
    в последний день месяца — поэтому число прижимается к длине месяца, а не
    переносится на первое число следующего.
    """
    if payment_day is None:
        return None
    import calendar

    year, month = today.year, today.month
    day = min(payment_day, calendar.monthrange(year, month)[1])
    candidate = date_(year, month, day)
    if candidate >= today:
        return candidate
    month += 1
    if month > 12:
        month, year = 1, year + 1
    return date_(year, month, min(payment_day, calendar.monthrange(year, month)[1]))
