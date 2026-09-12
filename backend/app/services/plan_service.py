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

Здесь план записывается один раз и разворачивается сам. Сумма плана — за
одно повторение, а в месяц попадает столько, сколько повторений в него
укладывается:

  * **разовый** — машина в мае 2027: одна сумма в один месяц;
  * **дневной** — столовая 300 ₽ в день, умноженная на число дней месяца.
    С признаком «только рабочие дни» — на число отработанных дней из
    work_periods, поэтому февраль пересчитывается сам;
  * **недельный** — «каждые две недели по понедельникам»: в месяце с тремя
    подходящими понедельниками повторений три;
  * **месячный** — связь 700 ₽: одно и то же, пока не изменишь. С шагом
    больше единицы — «раз в квартал»;
  * **годовой** — страховка в октябре, можно «в первый четверг октября».

Шаг («каждые N») работает одинаково у всех частот, а точка отсчёта — начало
самого раннего отрезка плана: «каждые две недели» без неё не имеет смысла.

Индексации нет нигде и намеренно. «Связь дорожает на 5% в год» звучит умно,
но в жизни цена меняется рывками и в непредсказуемые месяцы; когда она
изменилась, человек правит число, и оно действует с этого месяца вперёд —
прошлое не переписывается.
"""
import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.enums import CategoryKind, PlanFrequency, PlanMonthDay, TransactionType
from app.models.plan import Plan, PlanPeriod
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
        """Факт минус план — без нормализации знака.

        Смысл знака зависит от вида строки и потому остаётся за тем, кто
        показывает таблицу: у дохода плюс — перевыполнение, у расхода тот
        же плюс — перерасход. Нормализовать здесь означало бы, что сумма
        колонки перестала бы сходиться с суммой её клеток.
        """
        return self.actual - self.planned


@dataclass
class PlanRow:
    """Строка таблицы: категория и двенадцать её месяцев."""

    category_id: int | None
    name: str
    # Путь до корня ветки: «Зарплата · Иван». Показывается подсказкой при
    # наведении — в самой строке стоит короткое имя с отступом по глубине,
    # потому что путь целиком в каждой строке делает колонку нечитаемой.
    path: str
    # Глубина в дереве категорий: 0 — корень. Отступ рисуется по ней.
    depth: int
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


def weekdays_in_month(year: int, month: int) -> int:
    """Будни месяца: понедельник-пятница, без учёта праздников.

    Праздников здесь нет намеренно. Производственный календарь свой у
    каждой страны и меняется каждый год; держать его в приложении, которое
    человек ставит себе сам, значит обещать обновления, которых не будет.
    Ошибка в пару дней на плане меньше, чем ошибка от его отсутствия.

    Тому, у кого график не пятидневный, эта галочка не нужна — для него
    есть отработанные дни из work_periods.
    """
    return len(_workday_dates(year, month))


def _weekday_dates(year: int, month: int, weekday: int) -> list[date_]:
    """Все даты месяца, попадающие на этот день недели. 0 — понедельник."""
    first_weekday, total = calendar.monthrange(year, month)
    first_day = 1 + (weekday - first_weekday) % 7
    return [date_(year, month, day) for day in range(first_day, total + 1, 7)]


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date_ | None:
    """Первый, второй… или последний (−1) такой день недели в месяце.

    Пятый вторник есть не в каждом месяце, и в таком месяце повторения
    просто нет: подменять его четвёртым значило бы придумать за человека
    дату, которую он не называл.
    """
    dates = _weekday_dates(year, month, weekday)
    if nth == -1:
        return dates[-1]
    return dates[nth - 1] if 0 < nth <= len(dates) else None


def _workday_dates(year: int, month: int) -> list[date_]:
    """Будни месяца списком — понедельник-пятница, без учёта праздников."""
    total = days_in_month(year, month)
    return [
        date_(year, month, day)
        for day in range(1, total + 1)
        if date_(year, month, day).weekday() < 5
    ]


def _days_within_month(plan: Plan, year: int, month: int, anchor: date_) -> list[date_]:
    """Какие числа месяца берёт месячное или годовое повторение."""
    total = days_in_month(year, month)
    mode = plan.month_day_mode

    if mode is None:
        # Число не важно: одно повторение на том же числе, с которого план
        # начался. В коротком месяце — на последнем его дне: плана, которого
        # в феврале нет, человек, писавший «каждый месяц», не имел в виду.
        return [date_(year, month, min(anchor.day, total))]

    if mode is PlanMonthDay.DAY_OF_MONTH:
        # Числа только 1–28, поэтому проверять их существование не нужно —
        # но список приходит извне, и лишний месяц молча уронить нельзя.
        days = sorted(set(plan.month_days or [min(anchor.day, 28)]))
        return [date_(year, month, day) for day in days if day <= total]

    if mode is PlanMonthDay.NTH_WEEKDAY:
        nth = plan.nth_weekday or 1
        found = [
            _nth_weekday(year, month, weekday, nth)
            for weekday in sorted(set(plan.weekdays or [anchor.weekday()]))
        ]
        return [day for day in found if day is not None]

    if mode is PlanMonthDay.LAST_DAY:
        return [date_(year, month, total)]

    workdays = _workday_dates(year, month)
    if not workdays:
        return []
    return [workdays[0] if mode is PlanMonthDay.FIRST_WORKDAY else workdays[-1]]


def plan_anchor(plan: Plan) -> date_:
    """Точка отсчёта расписания — начало самого раннего отрезка.

    «Каждые две недели» без неё не имеет смысла: надо знать, от какой недели
    считать. Отдельного поля под это нет намеренно — человек уже ввёл дату
    начала, и второе такое же поле пришлось бы держать согласованным с
    первым, а разойдясь, они молча сдвинули бы весь план.
    """
    return min(period.valid_from for period in plan.periods)


def occurrence_dates(plan: Plan, year: int, month: int) -> list[date_]:
    """Даты повторений плана внутри месяца.

    Границы отрезков здесь не проверяются: какой отрезок действует в этом
    месяце, решает period_for_month, и делает это по месяцу, а не по дню —
    план, начатый 15-го, действует на весь месяц. Резать его здесь ещё раз,
    но уже по дням, значило бы считать первый месяц по-другому, чем все
    остальные.

    Точка отсчёта задаёт фазу: «каждые две недели» от 5 января — это 5, 19
    января, 2 февраля. До неё повторения тоже считаются — фаза у них та же,
    а действует план или нет, решают отрезки.
    """
    anchor = plan_anchor(plan)
    step = max(plan.repeat_every or 1, 1)
    total = days_in_month(year, month)

    if plan.kind is PlanFrequency.ONE_OFF:
        return [anchor] if (anchor.year, anchor.month) == (year, month) else []

    if plan.kind is PlanFrequency.DAY:
        return [
            day
            for day in (date_(year, month, number) for number in range(1, total + 1))
            if (day - anchor).days % step == 0
            and not (plan.skip_weekends and day.weekday() >= 5)
        ]

    if plan.kind is PlanFrequency.WEEK:
        wanted = set(plan.weekdays or [anchor.weekday()])
        anchor_week = anchor - timedelta(days=anchor.weekday())
        found = []
        for number in range(1, total + 1):
            day = date_(year, month, number)
            if day.weekday() not in wanted:
                continue
            week = day - timedelta(days=day.weekday())
            if ((week - anchor_week).days // 7) % step:
                continue
            found.append(day)
        return found

    if plan.kind is PlanFrequency.MONTH:
        if ((year - anchor.year) * 12 + month - anchor.month) % step:
            return []
        return _days_within_month(plan, year, month, anchor)

    # YEAR: шаг считается в годах, а месяц выбирается отдельно.
    if (year - anchor.year) % step:
        return []
    if month not in set(plan.months or [anchor.month]):
        return []
    return _days_within_month(plan, year, month, anchor)


def _roll_up_branches(rows: list[PlanRow], tree) -> None:
    """Строка родителя показывает всю ветку: себя и всех потомков.

    Так же считают дашборд и отчёты, и человек ждёт того же здесь: план
    стоит на «Администрации», а «Иван» над ней выглядел пустым, хотя
    деньги в ветке есть — просто строкой ниже.

    Меняются суммы только для показа. Итоги к этому моменту уже посчитаны
    по непересекающимся суммам (см. вызывающий код), иначе ветка вошла бы в
    них дважды.

    Потомок, у которого нет своей строки, ничего не добавляет — его деньги
    и так уже отнесены к ближайшему предку с планом, то есть учтены в
    чьей-то строке этой же ветки.
    """
    own = {
        row.category_id: [(cell.planned, cell.actual) for cell in row.months]
        for row in rows
        if row.category_id is not None
    }
    for row in rows:
        if row.category_id is None:
            continue
        children = [
            own[child]
            for child in tree.descendants_of(row.category_id)
            if child in own
        ]
        if not children:
            continue
        for index, cell in enumerate(row.months):
            cell.planned = sum((child[index][0] for child in children), cell.planned)
            cell.actual = sum((child[index][1] for child in children), cell.actual)


def period_for_month(plan: Plan, year: int, month: int):
    """Отрезок плана, действующий в этом месяце, или None.

    Границы сравниваются по месяцу, а не по дню: отрезок, начатый 15-го,
    действует на весь месяц. Половинчатый месяц требовал бы делить сумму на
    дни, а «связь 700 ₽ с середины марта» всё равно стоит 700.

    Перекрытий между отрезками не бывает — это проверяет схема, — поэтому
    подходящий ровно один, и брать первый найденный безопасно.
    """
    first = date_(year, month, 1)
    last = date_(year, month, days_in_month(year, month))
    for period in plan.periods:
        if period.valid_from > last:
            continue
        if period.valid_to is not None and period.valid_to < first:
            continue
        return period
    return None


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

    period = period_for_month(plan, year, month)
    if period is None:
        return Decimal("0")

    if plan.kind is PlanFrequency.ONE_OFF:
        # Разовая покупка стоит в своём месяце и больше нигде.
        return (
            period.amount
            if (period.valid_from.year, period.valid_from.month) == (year, month)
            else Decimal("0")
        )

    # «По отработанным дням» стоит особняком: это не календарное правило, а
    # факт из work_periods. Он вводится руками и появляется задним числом —
    # зато верен при любом графике, чего календарные «пн-пт» не дают ни
    # вахте, ни суткам через двое.
    #
    # Если план так помечен, а дней на месяц не введено, считаем по
    # календарным: лучше приблизительно, чем никак. Ноль дал бы пустой план
    # там, где траты есть, и человек искал бы ошибку в фактах.
    if plan.workdays_only:
        if workdays is not None:
            return period.amount * workdays
        return period.amount * days_in_month(year, month)

    # Всё остальное — расписание: сумма за одно повторение, умноженная на
    # число повторений, попавших в месяц.
    return period.amount * len(occurrence_dates(plan, year, month))


async def workdays_by_month(session: AsyncSession, year: int) -> dict[tuple[int, int], int]:
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
    plans = (
        (
            await session.execute(
                select(Plan).options(selectinload(Plan.periods)).where(Plan.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    tree = await load_category_tree(session)
    categories = {row.id: row for row in (await session.execute(select(Category))).scalars().all()}
    workdays = await workdays_by_month(session, year)

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


    def path_of(category_id: int) -> str:
        # ancestors_of идёт снизу вверх; для подписи нужен порядок сверху.
        chain = [
            categories[row].name for row in reversed(tree.ancestors_of(category_id)) if row in categories
        ]
        chain.append(categories[category_id].name)
        return " · ".join(chain)

    def row_for(category_id: int | None) -> PlanRow:
        if category_id not in rows:
            category = categories.get(category_id) if category_id is not None else None
            rows[category_id] = PlanRow(
                category_id=category_id,
                # План без категории — «прочее»: он есть, деньги обещаны, и
                # спрятать его значило бы недосчитать итог.
                name=category.name if category else "—",
                path=path_of(category_id) if category else "—",
                depth=len(tree.ancestors_of(category_id)) if category else 0,
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

    # Ветка обязана иметь вершину. Строка появляется только у категории, к
    # которой что-то отнесено, и родитель без собственных денег строки не
    # получал: в таблице оставалась подкатегория с отступом, висящая ни под
    # чем, — а после сворачивания веток вершине ещё и есть что показать.
    #
    # Добавленные так строки пустые, поэтому итоги, считаемые до
    # сворачивания, не меняются.
    for category_id in [row for row in rows if row is not None]:
        for ancestor in tree.ancestors_of(category_id):
            row_for(ancestor)

    ordered = sorted(
        rows.values(),
        # Доходы сверху: год читается как «сколько пришло, потом куда ушло».
        #
        # Внутри — по полному пути, а не по имени: так подкатегория встаёт
        # сразу под своим родителем, и отступ в таблице совпадает с
        # порядком строк. Сортировка по имени раскидывала ветку по всему
        # списку, и отступ читался как случайный.
        key=lambda row: (row.kind is not CategoryKind.INCOME, row.path),
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

    # Итоги считаются ДО сворачивания ветки, по непересекающимся суммам:
    # каждая строка держит только то, что отнесено лично к ней, и простое
    # сложение даёт верный итог. После сворачивания то же сложение задвоило
    # бы ветку — родитель и ребёнок показывали бы одни и те же деньги.
    income_totals = totals_of(income_rows)
    expense_totals = totals_of(expense_rows)

    _roll_up_branches(ordered, tree)
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


@dataclass
class WatchRow:
    """Строка списка наблюдения: категория и её двенадцать месяцев."""

    category_id: int
    name: str
    # Путь до корня ветки: «Продукты · Сладкое». Без него две «Воды» из
    # разных веток в списке неразличимы.
    path: str
    kind: CategoryKind
    months: list[Decimal] = field(default_factory=list)
    total: Decimal = Decimal("0")
    # Тот же итог за предыдущий год. Ради этого список и заводят: вопрос
    # не «сколько», а «больше или меньше, чем было».
    previous_total: Decimal = Decimal("0")


async def get_watchlist_overview(session: AsyncSession, year: int) -> dict:
    """Отмеченные категории по месяцам года плюс итог прошлого года.

    Замена листа «Отследить» из исходной таблицы, где несколько выбранных
    подкатегорий выписывались помесячно вручную.

    Суммы берутся по всей ветке: отметив «Продукты», человек хочет видеть
    и сыр, лежащий двумя уровнями ниже. Поэтому отмеченные родитель и его
    ребёнок дают пересекающиеся строки — так и задумано: целое и часть
    смотрят одновременно, а складывать строки между собой этот список и не
    предлагает.

    Плана здесь нет намеренно. Наблюдение отвечает на вопрос «сколько это
    у меня выходит», и требовать сначала завести план значило бы закрыть
    список от того, ради кого он нужен, — от человека, который ещё только
    присматривается к цифре.
    """
    watched = (
        (await session.execute(select(Category).where(Category.is_watched.is_(True))))
        .scalars()
        .all()
    )
    if not watched:
        return {"year": year, "rows": []}

    tree = await load_category_tree(session)
    names = {row.id: row.name for row in (await session.execute(select(Category))).scalars().all()}

    async def amounts(for_year: int) -> dict[CategoryKind, dict[tuple[int, int, int], Decimal]]:
        start = date_(for_year, 1, 1)
        end = date_(for_year, 12, 31)
        return {
            CategoryKind.INCOME: await monthly_amounts_by_category(
                session, transaction_type=TransactionType.INCOME, start_date=start, end_date=end
            ),
            CategoryKind.EXPENSE: await monthly_amounts_by_category(
                session, transaction_type=TransactionType.EXPENSE, start_date=start, end_date=end
            ),
        }

    current = await amounts(year)
    previous = await amounts(year - 1)

    def path_of(category_id: int) -> str:
        # ancestors_of идёт снизу вверх; для подписи нужен порядок сверху.
        chain = [names.get(row, "?") for row in reversed(tree.ancestors_of(category_id))]
        chain.append(names.get(category_id, "?"))
        return " · ".join(chain)

    rows: list[WatchRow] = []
    for category in sorted(watched, key=lambda row: (row.kind is not CategoryKind.INCOME, row.name)):
        branch = set(tree.subtree_of(category.id))
        source = current[category.kind]
        months = [
            sum(
                (
                    amount
                    for (row_year, row_month, row_category), amount in source.items()
                    if row_year == year and row_month == month and row_category in branch
                ),
                Decimal("0"),
            )
            for month in range(1, 13)
        ]
        previous_total = sum(
            (
                amount
                for (row_year, _, row_category), amount in previous[category.kind].items()
                if row_year == year - 1 and row_category in branch
            ),
            Decimal("0"),
        )
        rows.append(
            WatchRow(
                category_id=category.id,
                name=category.name,
                path=path_of(category.id),
                kind=category.kind,
                months=months,
                total=sum(months, Decimal("0")),
                previous_total=previous_total,
            )
        )

    return {"year": year, "rows": rows}


async def list_plans(session: AsyncSession) -> list[Plan]:
    # Категория подгружается сразу: в асинхронной сессии ленивая загрузка
    # отношения падает, а список планов без названий категорий бесполезен.
    # Отрезки — тоже сразу: без них план это категория без единой суммы, и
    # список планов показывал бы пустые строки.
    return list(
        (
            await session.execute(
                select(Plan)
                .options(selectinload(Plan.category), selectinload(Plan.periods))
                .order_by(Plan.id)
            )
        )
        .scalars()
        .all()
    )


async def create_plan(session: AsyncSession, payload: PlanCreate) -> Plan:
    data = payload.model_dump()
    periods = data.pop("periods")
    plan = Plan(**data)
    plan.periods = [PlanPeriod(**period) for period in periods]
    session.add(plan)
    await session.commit()
    return await _reload(session, plan.id)


async def _reload(session: AsyncSession, plan_id: int) -> Plan:
    """Перечитывает план вместе со связями.

    refresh() их не трогает, а в асинхронной сессии ленивая загрузка падает:
    ответ на создание плана разворачивал бы отрезки и ронял запрос.
    """
    stmt = (
        select(Plan)
        .options(selectinload(Plan.category), selectinload(Plan.periods))
        .where(Plan.id == plan_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def update_plan(session: AsyncSession, plan_id: int, payload: PlanUpdate) -> Plan:
    plan = await _reload(session, plan_id)
    updates = payload.model_dump(exclude_unset=True)
    # Отрезки заменяются целиком: правка приходит из формы, где список виден
    # весь, и «дополнить» означало бы, что удалённую строку нельзя удалить.
    periods = updates.pop("periods", None)
    for field_name, value in updates.items():
        setattr(plan, field_name, value)
    if periods is not None:
        plan.periods = [PlanPeriod(**period) for period in periods]
    await session.commit()
    return await _reload(session, plan_id)


async def delete_plan(session: AsyncSession, plan_id: int) -> None:
    """Удаляет план целиком.

    Чтобы прекратить план с определённого месяца, а не стереть его из
    истории, ставят `valid_to` у последнего отрезка: прошлое сравнение
    «план — факт» тогда остаётся правдой.
    """
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    await session.delete(plan)
    await session.commit()
