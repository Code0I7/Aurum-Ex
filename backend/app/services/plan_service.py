"""Планирование: чего ждём от года и что вышло на самом деле.

Отличается от бюджета, и обе вещи существуют одновременно. Бюджет — это
потолок на месяц, который предупреждает, когда его перешли. План —
ожидание, растянутое на годы, и отвечает он на другой вопрос: «каким
получится год», а не «не перебрал ли я прямо сейчас».

В исходной таблице планирование было листом на 48 строк, где каждый месяц —
пять колонок (план, % от дохода, факт, % от дохода, отклонение), а суммы
вроде «связь 700 ₽» приходилось вбивать в каждый из двенадцати столбцов
руками. Ежедневные траты — столовую по 300 ₽ — считали умножением в уме, и
февраль от января там ничем не отличался.

Здесь план записывается один раз и разворачивается сам:

  * **разовый** — машина в мае 2027: одна сумма в один месяц;
  * **ежемесячный** — связь 700 ₽: одно и то же, пока не изменишь;
  * **ежедневный** — столовая 300 ₽ в день, умноженная на число дней
    месяца. С признаком «только рабочие дни» — на число отработанных дней
    из work_periods, поэтому февраль пересчитывается сам.

Индексации нет нигде и намеренно. «Связь дорожает на 5% в год» звучит умно,
но в жизни цена меняется рывками и в непредсказуемые месяцы; когда она
изменилась, человек правит число, и оно действует с этого месяца вперёд —
прошлое не переписывается.
"""
import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.enums import CategoryKind, PlanKind, TransactionType
from app.models.plan import Plan
from app.models.work_period import WorkPeriod
from app.schemas.plan import PlanCreate, PlanUpdate
from app.services.category_rollup import monthly_amounts_by_category
from app.services.category_tree import load_category_tree


@dataclass
class MonthCell:
    """Одна клетка таблицы: сколько собирались и сколько вышло."""

    year: int
    month: int
    planned: Decimal = Decimal("0")
    actual: Decimal = Decimal("0")

    @property
    def deviation(self) -> Decimal:
        """Отклонение с точки зрения кошелька, а не арифметики.

        Для расхода перерасход — это минус, для дохода минус — недобор.
        Знак должен читаться одинаково в обеих половинах таблицы: минус
        всегда «хуже, чем собирались».
        """
        return self.actual - self.planned


@dataclass
class PlanRow:
    """Строка таблицы: категория и двенадцать её месяцев."""

    category_id: int | None
    name: str
    kind: CategoryKind
    months: list[MonthCell] = field(default_factory=list)

    @property
    def planned_total(self) -> Decimal:
        return sum((cell.planned for cell in self.months), Decimal("0"))

    @property
    def actual_total(self) -> Decimal:
        return sum((cell.actual for cell in self.months), Decimal("0"))


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def expand_plan(
    plan: Plan,
    year: int,
    month: int,
    workdays: int | None = None,
) -> Decimal:
    """Сколько этот план обещает на конкретный месяц.

    Ноль означает «в этом месяце план не действует» — он ещё не начался,
    уже отменён или это разовая покупка другого месяца.
    """
    if not plan.is_active:
        return Decimal("0")

    # Границы сравниваются по месяцу, а не по дню: план, начатый 15-го,
    # действует на весь месяц. Половинчатый месяц требовал бы делить сумму
    # на дни, а «связь 700 ₽ с середины марта» всё равно стоит 700.
    first = date_(year, month, 1)
    last = date_(year, month, days_in_month(year, month))
    if plan.valid_from > last:
        return Decimal("0")
    if plan.valid_to is not None and plan.valid_to < first:
        return Decimal("0")

    if plan.kind is PlanKind.ONE_OFF:
        # Разовая покупка стоит в своём месяце и больше нигде.
        return plan.amount if (plan.valid_from.year, plan.valid_from.month) == (year, month) else Decimal("0")

    if plan.kind is PlanKind.MONTHLY:
        return plan.amount

    # DAILY. Число дней берётся из отработанных, если план так помечен и
    # данные на месяц есть. Если не заданы — считаем по календарным: лучше
    # приблизительно, чем никак.
    if plan.workdays_only and workdays is not None:
        return plan.amount * workdays
    return plan.amount * days_in_month(year, month)


async def _workdays_by_month(session: AsyncSession, year: int) -> dict[tuple[int, int], int]:
    """Отработанные дни по месяцам года.

    Участник не различается: если планов у нескольких человек, дни всё
    равно берутся общие — иначе один незаполненный участник обнулил бы
    чужой план. Берётся максимум, а не сумма: два человека, отработавшие
    по 20 дней, не дают 40 рабочих дней в месяце.
    """
    rows = (
        await session.execute(
            select(WorkPeriod.year, WorkPeriod.month, WorkPeriod.workdays).where(
                WorkPeriod.year == year, WorkPeriod.workdays.is_not(None)
            )
        )
    ).all()
    result: dict[tuple[int, int], int] = {}
    for row_year, row_month, workdays in rows:
        key = (row_year, row_month)
        result[key] = max(result.get(key, 0), workdays)
    return result


async def get_plan_overview(session: AsyncSession, year: int) -> dict:
    """Таблица «план — факт — отклонение» за год.

    Возвращает строки по категориям, в которых есть хоть план, хоть факт.
    Категория без того и другого не показывается: пустая строка на год
    занимает место и ничего не сообщает.
    """
    plans = (await session.execute(select(Plan).where(Plan.is_active.is_(True)))).scalars().all()
    tree = await load_category_tree(session)
    categories = {row.id: row for row in (await session.execute(select(Category))).scalars().all()}
    workdays = await _workdays_by_month(session, year)

    start = date_(year, 1, 1)
    end = date_(year, 12, 31)
    actual_income = await monthly_amounts_by_category(
        session, transaction_type=TransactionType.INCOME, start_date=start, end_date=end
    )
    actual_expense = await monthly_amounts_by_category(
        session, transaction_type=TransactionType.EXPENSE, start_date=start, end_date=end
    )

    # Плановые суммы по (категория, месяц). Несколько планов на одну
    # категорию складываются: «связь 700» и «интернет 500» — это две записи,
    # а строка в таблице одна.
    planned: dict[tuple[int | None, int], Decimal] = defaultdict(Decimal)
    for plan in plans:
        for month in range(1, 13):
            amount = expand_plan(plan, year, month, workdays.get((year, month)))
            if amount:
                planned[(plan.category_id, month)] += amount

    rows: dict[int | None, PlanRow] = {}


    def row_for(category_id: int | None) -> PlanRow:
        if category_id not in rows:
            category = categories.get(category_id) if category_id is not None else None
            rows[category_id] = PlanRow(
                category_id=category_id,
                # План без категории — «прочее»: он есть, деньги обещаны, и
                # спрятать его значило бы недосчитать итог.
                name=category.name if category else "—",
                kind=category.kind if category else CategoryKind.EXPENSE,
                months=[MonthCell(year=year, month=month) for month in range(1, 13)],
            )
        return rows[category_id]

    for (category_id, month), amount in planned.items():
        row_for(category_id).months[month - 1].planned += amount

    # Категории, на которых вообще стоит хоть один план: по ним решается,
    # к какой строке отнести факт.
    planned_categories = {category_id for category_id, _ in planned}

    def target_row(category: Category) -> int:
        """К какой строке отнести трату.

        План может стоять на любом уровне ветки. Правило: факт идёт к
        ближайшему предку, у которого план есть, — так план на «Продуктах»
        собирает и сыр, лежащий двумя уровнями ниже, а план на «Молочном»
        перехватывает его раньше, потому что он ближе. Если плана нет нигде
        по всей ветке — к корню, как в отчётах и на дашборде.
        """
        if category.id in planned_categories:
            return category.id
        for ancestor in tree.ancestors_of(category.id):
            if ancestor in planned_categories:
                return ancestor
        return tree.top_level_of(category.id)

    # Категория, у которой плана нет, всё равно попадает в таблицу:
    # незапланированная трата — это ровно то, что планирование должно
    # показывать.
    for source in (actual_income, actual_expense):
        for (row_year, month, category_id), amount in source.items():
            if row_year != year:
                continue
            category = categories.get(category_id)
            if category is None:
                continue
            target = target_row(category)
            entry = row_for(target)
            entry.months[month - 1].actual += amount

    ordered = sorted(
        rows.values(),
        # Доходы сверху: год читается как «сколько пришло, потом куда ушло».
        key=lambda row: (row.kind is not CategoryKind.INCOME, row.name),
    )

    income_rows = [row for row in ordered if row.kind is CategoryKind.INCOME]
    expense_rows = [row for row in ordered if row.kind is not CategoryKind.INCOME]

    def totals_of(source: list[PlanRow]) -> list[MonthCell]:
        return [
            MonthCell(
                year=year,
                month=month,
                planned=sum((row.months[month - 1].planned for row in source), Decimal("0")),
                actual=sum((row.months[month - 1].actual for row in source), Decimal("0")),
            )
            for month in range(1, 13)
        ]

    income_totals = totals_of(income_rows)
    expense_totals = totals_of(expense_rows)
    # Свободные средства: то, что осталось бы, если бы всё шло по плану, и
    # то, что осталось на самом деле.
    free = [
        MonthCell(
            year=year,
            month=month,
            planned=income_totals[month - 1].planned - expense_totals[month - 1].planned,
            actual=income_totals[month - 1].actual - expense_totals[month - 1].actual,
        )
        for month in range(1, 13)
    ]

    return {
        "year": year,
        "rows": ordered,
        "income_totals": income_totals,
        "expense_totals": expense_totals,
        "free_totals": free,
    }


async def list_plans(session: AsyncSession) -> list[Plan]:
    # Категория подгружается сразу: в асинхронной сессии ленивая загрузка
    # отношения падает, а список планов без названий категорий бесполезен.
    return list(
        (
            await session.execute(
                select(Plan).options(selectinload(Plan.category)).order_by(Plan.valid_from, Plan.id)
            )
        )
        .scalars()
        .all()
    )


async def create_plan(session: AsyncSession, payload: PlanCreate) -> Plan:
    plan = Plan(**payload.model_dump())
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


async def update_plan(session: AsyncSession, plan_id: int, payload: PlanUpdate) -> Plan:
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field_name, value)
    await session.commit()
    await session.refresh(plan)
    return plan


async def delete_plan(session: AsyncSession, plan_id: int) -> None:
    """Удаляет план целиком.

    Чтобы прекратить план с определённого месяца, а не стереть его из
    истории, ставят `valid_to`: прошлое сравнение «план — факт» тогда
    остаётся правдой.
    """
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    await session.delete(plan)
    await session.commit()
