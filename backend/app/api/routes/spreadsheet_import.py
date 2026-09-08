"""Перенос истории из табличного учёта: предпросмотр и применение.

Два шага, а не один, намеренно. Импорт четырёх лет чужой истории — операция,
которую делают один раз и не откатывают: человек должен сначала увидеть,
что получится, и только потом согласиться. Предпросмотр ничего не пишет.

Применение доступно только на пустой базе. Второй импорт поверх
существующих данных удвоил бы всю историю, а разобрать потом, какая из двух
одинаковых поездок на автобусе лишняя, невозможно.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.transaction import Transaction
from app.services.currency_service import get_base_currency
from app.services.spreadsheet_import_service import ImportPlan, apply_plan, build_plan, parse_settings_csv

router = APIRouter(prefix="/import/spreadsheet", tags=["import"])

# Ограничение на размер выгрузки. Лист транзакций за четыре года — около
# 700 КБ; десять мегабайт с запасом покрывают и десятилетнюю историю, но не
# дают положить сервер случайным гигабайтом.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class IssueOut(BaseModel):
    row: int
    reason: str
    detail: str = ""


class PlanOut(BaseModel):
    """Отчёт о том, что произойдёт при импорте."""

    incomes: int
    expenses: int
    transfers: int
    goal_contributions: int
    excluded: int
    opening_balances: dict[str, str]
    accounts: list[str]
    categories: int
    subcategories: int
    participants: list[str]
    # Заполняются только если приложен лист настроек.
    stores: list[str] = []
    work_years: list[int] = []
    goals: int
    total_rows: int
    # Счета, опознанные как кредитные по начисленным на них процентам. Это
    # догадка, и показывается она отдельным списком именно поэтому: человек
    # должен увидеть её до импорта и поправить, если счёт попал сюда потому,
    # что с него однажды заплатили проценты по чужому кредиту.
    credit_accounts: list[str] = []
    issues: list[IssueOut]
    # Можно ли применять: непустая база блокирует импорт.
    can_apply: bool
    existing_transactions: int


class ResultOut(BaseModel):
    accounts: int
    categories: int
    participants: int
    goals: int
    transactions: int
    transfers: int
    goal_contributions: int
    work_periods: int = 0
    issues: list[IssueOut]


async def _read_csv(file: UploadFile) -> str:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 10 МБ")
    # Google Sheets отдаёт UTF-8, но выгрузка через Excel может прийти в
    # UTF-8 с BOM — utf-8-sig снимает и его, и обычный UTF-8 читает как есть.
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Файл не в кодировке UTF-8") from None


async def _existing_transactions(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Transaction))).scalar_one())


def _to_plan_out(plan: ImportPlan, existing: int, sheet=None) -> PlanOut:
    excluded = sum(1 for row in (*plan.incomes, *plan.expenses) if row.is_excluded)
    return PlanOut(
        incomes=len(plan.incomes),
        expenses=len(plan.expenses),
        transfers=len(plan.transfers),
        goal_contributions=len(plan.reserves) + len(plan.releases),
        excluded=excluded,
        opening_balances={name: str(value) for name, value in plan.accounts.items() if value},
        accounts=sorted(plan.accounts),
        categories=len(plan.categories),
        subcategories=sum(len(children) for children in plan.categories.values()),
        participants=sorted(set(plan.participants) | set(sheet.participants if sheet else [])),
        stores=sorted(sheet.stores) if sheet else [],
        work_years=sorted(sheet.work_hours_by_year) if sheet else [],
        goals=len(plan.goals),
        total_rows=plan.total_rows,
        credit_accounts=sorted(plan.credit_accounts),
        issues=[IssueOut(row=issue.row, reason=issue.reason, detail=issue.detail) for issue in plan.issues],
        can_apply=existing == 0,
        existing_transactions=existing,
    )


@router.post("/preview", response_model=PlanOut)
async def preview_import(
    transactions: UploadFile = File(...),
    settings: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
) -> PlanOut:
    """Разбирает выгрузку и показывает, что получится. Ничего не пишет.

    Лист настроек необязателен: без него счета получают вид по догадке из
    названия и общую валюту, с ним — то, что указано в таблице прямо."""
    content = await _read_csv(transactions)
    plan = build_plan(content)
    sheet = parse_settings_csv(await _read_csv(settings)) if settings is not None else None
    return _to_plan_out(plan, await _existing_transactions(session), sheet)


@router.post("/apply", response_model=ResultOut)
async def apply_import(
    transactions: UploadFile = File(...),
    settings: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
) -> ResultOut:
    """Переносит историю. Работает только на пустой базе."""
    existing = await _existing_transactions(session)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"В базе уже {existing} операций. Импорт возможен только на пустой установке — "
                "иначе история удвоится, и разобрать, какая запись лишняя, будет невозможно."
            ),
        )

    content = await _read_csv(transactions)
    plan = build_plan(content)
    sheet = parse_settings_csv(await _read_csv(settings)) if settings is not None else None
    result = await apply_plan(session, plan, await get_base_currency(session), sheet)

    return ResultOut(
        accounts=result.accounts,
        categories=result.categories,
        participants=result.participants,
        goals=result.goals,
        transactions=result.transactions,
        transfers=result.transfers,
        goal_contributions=result.goal_contributions,
        work_periods=result.work_periods,
        issues=[IssueOut(row=issue.row, reason=issue.reason, detail=issue.detail) for issue in result.issues],
    )
