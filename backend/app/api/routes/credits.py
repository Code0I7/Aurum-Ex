"""Условия по кредитам.

Вложены в счёт (`/accounts/{id}/credit-terms`), а не вынесены в отдельный
ресурс: условия не существуют сами по себе, у них нет собственного имени и
баланса — это дополнение к счёту, и адрес должен это показывать. Отдельно
стоит только сводный список `/credits`, потому что страница долгов
спрашивает «какие вообще кредиты есть», не зная заранее номеров счетов.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.credit import (
    CreditPlanRequest,
    CreditPlanResponse,
    CreditSummary,
    CreditTermsRead,
    CreditTermsWrite,
)
from app.services.credit_plan_service import build_plan
from app.services.credit_service import (
    delete_credit_terms,
    get_credit_summary,
    get_credit_terms,
    list_credit_terms,
    save_credit_terms,
)

router = APIRouter(tags=["credits"])


@router.get("/credits", response_model=list[CreditTermsRead])
async def read_credits(session: AsyncSession = Depends(get_session)) -> list[CreditTermsRead]:
    return await list_credit_terms(session)


@router.get("/credits/summary", response_model=CreditSummary)
async def read_credit_summary(session: AsyncSession = Depends(get_session)) -> CreditSummary:
    totals = await get_credit_summary(session)
    return CreditSummary(
        debt=totals["debt"],
        estimated_monthly_interest=totals["estimated_monthly_interest"],
    )


@router.post("/credits/plan", response_model=CreditPlanResponse)
async def plan_credit(payload: CreditPlanRequest) -> CreditPlanResponse:
    """Калькулятор: «взял столько-то — что будет дальше».

    Ничего не читает и не пишет, поэтому и сессия не нужна. Живёт на
    сервере, а не в браузере, по одной причине: расчёт переплаты — то
    место, где ошибка стоит дорого, а на сервере он покрыт тестами.
    """
    return build_plan(payload)


@router.get("/accounts/{account_id}/credit-terms", response_model=CreditTermsRead)
async def read_credit_terms(
    account_id: int, session: AsyncSession = Depends(get_session)
) -> CreditTermsRead:
    terms = await get_credit_terms(session, account_id)
    if terms is None:
        # 404, а не пустой объект: «условия не заданы» и «ставка равна нулю» —
        # разные вещи, и интерфейс должен их различать.
        raise HTTPException(status_code=404, detail="Credit terms not set")
    return terms


@router.put("/accounts/{account_id}/credit-terms", response_model=CreditTermsRead)
async def write_credit_terms(
    account_id: int, payload: CreditTermsWrite, session: AsyncSession = Depends(get_session)
) -> CreditTermsRead:
    return await save_credit_terms(session, account_id, payload)


@router.delete("/accounts/{account_id}/credit-terms", status_code=204)
async def remove_credit_terms(account_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_credit_terms(session, account_id)
