"""A planned amount for a category — what the user intends to spend or earn,
against which the actual figures are compared.

Different from Budget (models/budget.py), and both exist. A budget is a
monthly ceiling that raises a warning when crossed; a plan is an expectation
stretched over years, used to answer "what will the year look like" rather
than "am I over the limit right now".

Сумма плана — за одно повторение, а в месяц попадает столько, сколько
повторений в него укладывается:

  * ONE_OFF — машина в мае 2027: одна сумма в один месяц;
  * DAY — столовая 300 ₽ в день × дни месяца. При `skip_weekends` — по
    будням календаря, при `workdays_only` — по отработанным дням из
    work_periods (см. models/work_period.py). В феврале пересчитывается
    сама;
  * WEEK — «каждые две недели по понедельникам»: в месяце с тремя
    понедельниками повторений три;
  * MONTH — связь 700 ₽: одно и то же каждый месяц, пока не изменишь. С
    шагом больше единицы — «раз в квартал»;
  * YEAR — страховка в октябре: раз в год, можно «в первый четверг».

Шаг лежит в `repeat_every` и работает одинаково у всех частот. Точка
отсчёта — начало самого раннего отрезка: «каждые две недели» без неё не
имеет смысла, а отдельное поле под неё дублировало бы дату, которую человек
уже ввёл.

No automatic indexation anywhere. When a price rises the user edits the
number and it applies from that month forward — the past is never rewritten.
Гибкость тут стоила бы точности: "связь дорожает на 5% в год" звучит умно,
но в жизни цена меняется рывками и в непредсказуемые месяцы.
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PlanFrequency, PlanMonthDay
from app.models.mixins import TimestampMixin


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Категория, к которой относится план. SET NULL, как и везде: удаление
    # категории не должно ломать чтение плана.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Персона, если план личный. Пусто — план общий по домохозяйству.
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )

    # Частота повторения. Колонка осталась `kind`: это по-прежнему вид
    # плана, просто видов стало больше, а переименование живой колонки
    # ломало бы старые выгрузки ради одного слова.
    kind: Mapped[PlanFrequency] = mapped_column(
        Enum(PlanFrequency, name="plan_kind", native_enum=False, length=10), nullable=False
    )

    # Шаг: «каждые N». Единица у всех частот означает «каждый» — каждый
    # день, каждую неделю, каждый месяц.
    #
    # Потолок 365 стоит на всех частотах одинаково и взят с запасом: «каждые
    # 36 месяцев» человек завести может, а полтора года шагом не выражаются
    # никак, поэтому запрещать что-то осмысленное здесь не за что.
    repeat_every: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # Дни недели, 0 — понедельник. Для WEEK — по каким дням повторяется, для
    # NTH_WEEKDAY — какой день недели искать в месяце.
    #
    # Пусто означает «по тому же дню недели, с которого план начался»: так
    # ведёт себя стандарт календарей, и так человек и думает, заводя
    # «каждые две недели» с конкретной даты.
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    # Как выбирается день внутри месяца у MONTH и YEAR. Пусто — «число не
    # важно»: одно повторение на том же числе, с которого план начался.
    month_day_mode: Mapped[PlanMonthDay | None] = mapped_column(
        Enum(PlanMonthDay, name="plan_month_day", native_enum=False, length=20), nullable=True
    )

    # Числа месяца для DAY_OF_MONTH, 1–28. Несколько — «плачу 1-го и 15-го».
    month_days: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    # Номер дня недели в месяце для NTH_WEEKDAY: 1–5, а −1 — последний.
    # Пятый вторник есть не в каждом месяце, и в таком месяце повторения
    # просто нет: подменять его четвёртым значило бы придумать за человека.
    nth_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Месяцы для YEAR, 1–12. Пусто — тот же месяц, с которого план начался.
    months: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    # Только для DAY: пропускать субботу и воскресенье. Пришло на смену
    # прежнему `weekdays_only` и означает то же самое — будни календаря, без
    # праздников, — но работает и с шагом больше единицы.
    skip_weekends: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    # Только для DAILY: считать по отработанным дням вместо календарных.
    # Рабочая столовая по выходным не работает, и календарные дни завышали
    # бы план почти в полтора раза.
    #
    # Число дней берётся из work_periods, а НЕ из производственного
    # календаря: график у людей разный. Сутки через двое, вахта, четыре дня
    # в неделю — календарные "пн-пт" для всех них неверны, а введённое
    # человеком число верно всегда. Если на месяц дней не задано, план
    # считается по календарным дням: лучше приблизительно, чем никак.
    # Взаимоисключающе со `skip_weekends`, потому что это разные вопросы.
    # «Отработанные дни» — факт из work_periods, он появляется задним числом
    # и его надо вводить руками. «Будни» — календарь, он известен на годы
    # вперёд и не требует ничего вводить. Столовая при пятидневке
    # описывается вторым, а вахта — первым.
    workdays_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category: Mapped["Category | None"] = relationship()
    participant: Mapped["Participant | None"] = relationship()
    periods: Mapped[list["PlanPeriod"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanPeriod.valid_from"
    )


class PlanPeriod(Base, TimestampMixin):
    """Сумма плана на отрезке времени.

    Раньше сумма и период жили прямо в плане, и смена тарифа означала второй
    план: та же категория, тот же вид, другая сумма и другие даты. За
    несколько лет от «связи 700 ₽» оставался десяток записей с одинаковым
    названием, и понять, какая из них действует сейчас, можно было только
    сверив даты у всех.

    Теперь план — это категория и способ счёта, а суммы лежат внутри
    списком. Заметка у периода отвечает на вопрос «почему поменялось»:
    «подорожал тариф», «сменил оператора». У плана своя заметка осталась —
    она про план целиком.

    Отрезки не должны перекрываться — проверяется в схеме: на один месяц
    приложение обязано знать одну сумму, а выбирать за человека, какая из
    двух главнее, значило бы врать в таблице года.
    """

    __tablename__ = "plan_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)

    # Для ONE_OFF и MONTHLY — сумма на месяц, для DAILY — сумма на день.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Для ONE_OFF обе даты попадают в один месяц; у последнего отрезка
    # MONTHLY и DAILY `valid_to` пустая, пока план не отменён, — так один
    # отрезок покрывает сколько угодно лет вперёд.
    valid_from: Mapped[date_] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date_ | None] = mapped_column(Date, nullable=True)

    # Причина смены суммы. Необязательна: через год «почему тут 900» —
    # вопрос, на который никто уже не ответит, но заставлять писать ответ
    # заранее значит получить в поле точку.
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Пометка «убрать с глаз» — и только. Помеченный отрезок считается ровно
    # так же и в таблице года стоит на своём месте: спрятать число и
    # перестать его считать — разные вещи, и путать их в учёте нельзя.
    #
    # Нужна потому, что список отрезков растёт и не убывает: тариф менялся
    # четыре раза за три года, в форме четыре строки, живая одна.
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    plan: Mapped["Plan"] = relationship(back_populates="periods")
