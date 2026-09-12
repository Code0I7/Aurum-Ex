"""Цели накопления.

Сумма цели не хранится, а складывается из журнала взносов при каждом
чтении: хранимый итог рано или поздно разъезжается с журналом, и починить
это можно только пересчётом — то есть тем же действием, только позже и
после того, как человек увидел неправду.

Отложенное — не отдельный кошелёк, а **пометка на деньгах счёта**. Взнос
никуда ничего не перекладывает; он лишь говорит, что часть остатка обещана
другой задаче. Отсюда три числа у счёта: всего, отложено, доступно.

Каждый взнос знает свой счёт. Иначе «три тысячи наличными, две безналом»
неотличимо от «пять тысяч непонятно откуда», и вернуть с наличных можно
было бы больше, чем с них откладывали.

Цель завершается вручную и двумя разными способами. Деньги ушли на то,
ради чего копились, — ACHIEVED; передумали и вернули — CANCELLED. Оба
снимают резерв, но по противоположным причинам, и в исходной таблице их
различал только текст комментария.

Важное следствие: закрытие цели **ничего не вычитает со счёта**. Деньги
уже ушли обычной тратой; вычесть их ещё раз значило бы посчитать расход
дважды. Отрезок резерва просто исчезает.
"""
from collections import defaultdict
from datetime import date as date_
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import GoalStatus
from app.models.goal import Goal, GoalContribution
from app.schemas.goal import (
    AccountReservation,
    GoalContributionCreate,
    GoalCreate,
    GoalRead,
    GoalReservation,
    GoalUpdate,
)

_SELECT_WITH_TOTAL = (
    select(
        Goal.id,
        Goal.name,
        Goal.target_amount,
        Goal.started_on,
        Goal.planned_on,
        Goal.account_id,
        Goal.status,
        Goal.closed_at,
        func.coalesce(func.sum(GoalContribution.amount), 0).label("current_amount"),
        func.coalesce(
            func.sum(case((GoalContribution.amount > 0, GoalContribution.amount), else_=0)), 0
        ).label("deposited"),
    )
    .outerjoin(GoalContribution, GoalContribution.goal_id == Goal.id)
    .group_by(
        Goal.id,
        Goal.name,
        Goal.target_amount,
        Goal.started_on,
        Goal.planned_on,
        Goal.account_id,
        Goal.status,
        Goal.closed_at,
        Goal.created_at,
    )
    .order_by(Goal.created_at)
)


def _days_between(start: date_ | None, end: date_ | None) -> int | None:
    """Дней от одной даты до другой. None, если хоть одной из них нет:
    ноль здесь означал бы «собрали за день», а это не то же самое, что
    «не знаем, когда начали»."""
    if start is None or end is None:
        return None
    return (end - start).days


def _goal_days(
    started_on: date_ | None,
    planned_on: date_ | None,
    closed_at: date_ | None,
    status: GoalStatus,
) -> tuple[int | None, int | None, int | None]:
    """Три числа, которые получаются из трёх дат.

    Незавершённая цель считается до сегодня, завершённая — до дня сбора:
    иначе «копил 40 дней» продолжало бы расти у цели, закрытой год назад.

    Срок до планируемой даты у завершённой цели не считается вовсе: он уже
    ни на что не влияет, а «просрочено на 300 дней» у выполненной цели —
    упрёк за то, чего давно нет.

    «За сколько собрали» есть только у достигнутой: у отменённой сбора не
    было, был отказ.
    """
    today = date_.today()
    finished = closed_at is not None

    days_saving = _days_between(started_on, closed_at if finished else today)
    days_to_plan = None if finished else _days_between(today, planned_on)
    days_taken = _days_between(started_on, closed_at) if status is GoalStatus.ACHIEVED else None
    return days_saving, days_to_plan, days_taken


def _to_read(row: Row, by_account: list[GoalReservation]) -> GoalRead:
    current = row.current_amount
    target = row.target_amount
    percent = float(current / target * 100) if target else 0.0
    days_saving, days_to_plan, days_taken = _goal_days(
        row.started_on, row.planned_on, row.closed_at, row.status
    )
    return GoalRead(
        id=row.id,
        name=row.name,
        target_amount=target,
        started_on=row.started_on,
        planned_on=row.planned_on,
        account_id=row.account_id,
        status=row.status,
        closed_at=row.closed_at,
        days_saving=days_saving,
        days_to_plan=days_to_plan,
        days_taken=days_taken,
        current_amount=current,
        deposited=row.deposited,
        remaining=target - current,
        percent=percent,
        is_reached=current >= target,
        by_account=by_account,
    )


async def _by_account(session: AsyncSession, goal_ids: list[int]) -> dict[int, list[GoalReservation]]:
    """Сколько каждой целью отложено на каждом счёте.

    Одним запросом на весь список, а не по запросу на цель: пятнадцать
    целей — это пятнадцать лишних обращений к базе ради строчки под
    полосой прогресса.

    Нулевые и отрицательные суммы отбрасываются: счёт, с которого сначала
    отложили, а потом вернули столько же, в списке «откуда отложено» не
    участвует — он там ничего не держит.
    """
    if not goal_ids:
        return {}
    rows = (
        await session.execute(
            select(
                GoalContribution.goal_id,
                GoalContribution.account_id,
                Account.name,
                func.sum(GoalContribution.amount).label("amount"),
            )
            .join(Account, Account.id == GoalContribution.account_id)
            .where(GoalContribution.goal_id.in_(goal_ids))
            .group_by(GoalContribution.goal_id, GoalContribution.account_id, Account.name)
            .order_by(Account.name)
        )
    ).all()

    result: dict[int, list[GoalReservation]] = defaultdict(list)
    for goal_id, account_id, account_name, amount in rows:
        if amount <= 0:
            continue
        result[goal_id].append(
            GoalReservation(account_id=account_id, account_name=account_name, amount=amount)
        )
    return result


async def _read_one(session: AsyncSession, goal_id: int) -> GoalRead:
    row = (await session.execute(_SELECT_WITH_TOTAL.where(Goal.id == goal_id))).one()
    return _to_read(row, (await _by_account(session, [goal_id])).get(goal_id, []))


async def list_goals(session: AsyncSession) -> list[GoalRead]:
    rows = (await session.execute(_SELECT_WITH_TOTAL)).all()
    breakdown = await _by_account(session, [row.id for row in rows])
    return [_to_read(row, breakdown.get(row.id, [])) for row in rows]


async def list_reservations(session: AsyncSession) -> list[AccountReservation]:
    """Чем занята часть остатка на каждом счёте — по целям.

    Нужно обзору: полоса счёта показывает доступное одним цветом, а
    отложенное — отдельными отрезками с подписью, на что именно. Без
    разбивки по целям отрезок был бы один и не отвечал на вопрос «а это
    что».

    Только активные цели: завершённая ничего не держит. Деньги достигнутой
    уже потрачены обычной тратой, у отменённой — возвращены в общий
    остаток.
    """
    rows = (
        await session.execute(
            select(
                GoalContribution.account_id,
                Goal.id,
                Goal.name,
                func.sum(GoalContribution.amount).label("amount"),
            )
            .join(Goal, Goal.id == GoalContribution.goal_id)
            .where(
                GoalContribution.account_id.is_not(None),
                Goal.status == GoalStatus.ACTIVE,
            )
            .group_by(GoalContribution.account_id, Goal.id, Goal.name)
            .order_by(func.sum(GoalContribution.amount).desc())
        )
    ).all()
    return [
        AccountReservation(account_id=account_id, goal_id=goal_id, goal_name=name, amount=amount)
        for account_id, goal_id, name, amount in rows
        if amount > 0
    ]


async def create_goal(session: AsyncSession, payload: GoalCreate) -> GoalRead:
    goal = Goal(
        name=payload.name,
        target_amount=payload.target_amount,
        started_on=payload.started_on,
        planned_on=payload.planned_on,
        account_id=payload.account_id,
    )
    session.add(goal)
    await session.commit()
    # Числа из дат считаются той же функцией, что и при чтении списка:
    # только что созданная цель обязана отвечать то же самое, что ответит
    # через секунду на обновлении страницы.
    days_saving, days_to_plan, days_taken = _goal_days(
        goal.started_on, goal.planned_on, goal.closed_at, goal.status
    )
    return GoalRead(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        started_on=goal.started_on,
        planned_on=goal.planned_on,
        account_id=goal.account_id,
        status=goal.status,
        closed_at=goal.closed_at,
        days_saving=days_saving,
        days_to_plan=days_to_plan,
        days_taken=days_taken,
        current_amount=Decimal("0"),
        deposited=Decimal("0"),
        remaining=goal.target_amount,
        percent=0.0,
        is_reached=False,
    )


async def update_goal(session: AsyncSession, goal_id: int, payload: GoalUpdate) -> GoalRead:
    goal = await session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        new_status = updates["status"]
        # Дата завершения ставится вместе со статусом — сегодняшняя, как
        # умолчание. Приложение знает день, когда нажали кнопку, а не день,
        # когда деньги собрались, и поправить её потом можно руками (поле
        # closed_at в GoalUpdate). Если правка пришла тем же запросом, она
        # побеждает: цикл ниже перезапишет умолчание.
        #
        # Возврат в работу дату снимает — иначе цель, открытая заново,
        # осталась бы с датой конца, которого не было.
        goal.closed_at = date_.today() if new_status is not GoalStatus.ACTIVE else None
    for field, value in updates.items():
        setattr(goal, field, value)
    await session.commit()
    return await _read_one(session, goal_id)


async def delete_goal(session: AsyncSession, goal_id: int) -> None:
    goal = await session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    await session.delete(goal)
    await session.commit()


async def add_contribution(session: AsyncSession, goal_id: int, payload: GoalContributionCreate) -> GoalRead:
    goal = await session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Счёт взноса: указанный или, если не указан, счёт самой цели — так
    # ведёт себя привычный случай «одна цель, одна карта», и заставлять
    # выбирать счёт там, где он и так один, незачем.
    account_id = payload.account_id if payload.account_id is not None else goal.account_id

    if payload.amount < 0 and account_id is not None:
        # Вернуть можно только то, что с этого счёта откладывали. Иначе
        # «отложил 3 000 наличными и 2 000 безналом, вернул 4 000
        # наличными» проходит молча, и на наличных повисает минус тысяча
        # резерва — остаток счёта после этого врёт.
        reserved = (
            await session.execute(
                select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
                    GoalContribution.goal_id == goal_id,
                    GoalContribution.account_id == account_id,
                )
            )
        ).scalar_one()
        if -payload.amount > reserved:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot return more than was set aside from this account: "
                    f"reserved {reserved}, requested {-payload.amount}"
                ),
            )

    session.add(
        GoalContribution(
            goal_id=goal_id,
            amount=payload.amount,
            date=payload.date,
            note=payload.note,
            account_id=account_id,
        )
    )
    await session.commit()
    return await _read_one(session, goal_id)
