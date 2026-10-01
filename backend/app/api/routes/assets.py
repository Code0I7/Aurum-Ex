from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.models.asset import Asset, AssetValuation
from app.schemas.asset import (
    AssetBase,
    AssetCreate,
    AssetRead,
    AssetUpdate,
    AssetValuationCreate,
    AssetValuationRead,
    AssetValuationUpdate,
)
from app.services.currency_service import get_base_currency

router = APIRouter(prefix="/assets", tags=["assets"])

_EAGER = (selectinload(Asset.valuations),)


def _to_read(asset: Asset) -> AssetRead:
    """Ответ собирается по списку полей схемы, а не по памяти автора.

    Перечисленные руками, они однажды разошлись: `is_personal_use` в этот
    список не попал, и флаг не возвращался никогда. Форма правки читает
    ответ, видит пусто и при следующем сохранении отправляет «нет» — то
    есть отметка не только не показывалась, но и стиралась. Теперь новое
    поле схемы попадает в ответ само.
    """
    latest = asset.valuations[-1] if asset.valuations else None
    stored = {field: getattr(asset, field) for field in AssetBase.model_fields}
    return AssetRead(
        **stored,
        id=asset.id,
        current_value=latest.value if latest else 0,
        as_of_date=latest.as_of_date if latest else asset.created_at.date(),
    )


@router.get("", response_model=list[AssetRead])
async def list_assets(session: AsyncSession = Depends(get_session)) -> list[AssetRead]:
    result = await session.execute(select(Asset).options(*_EAGER).order_by(Asset.name))
    return [_to_read(asset) for asset in result.scalars().all()]


@router.post("", response_model=AssetRead, status_code=201)
async def create_asset(payload: AssetCreate, session: AsyncSession = Depends(get_session)) -> AssetRead:
    # Поля — из схемы, по той же причине, что и в _to_read: перечисленные
    # руками, они теряли «личное пользование» при каждом создании.
    data = payload.model_dump(exclude={"value", "as_of_date"})
    # Валюта по умолчанию — валюта установки, как у счёта. Имущество за
    # границей бывает, но это редкий случай, а не умолчание.
    if not data.get("currency"):
        data["currency"] = (await get_base_currency(session)).upper()
    asset = Asset(**data)
    session.add(asset)
    await session.flush()
    session.add(AssetValuation(asset_id=asset.id, value=payload.value, as_of_date=payload.as_of_date))
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset.id))
    return _to_read(refreshed.scalar_one())


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(asset_id: int, payload: AssetUpdate, session: AsyncSession = Depends(get_session)) -> AssetRead:
    result = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    await session.commit()
    await session.refresh(asset, attribute_names=["valuations"])
    return _to_read(asset)


@router.post("/{asset_id}/valuations", response_model=AssetRead)
async def add_asset_valuation(
    asset_id: int, payload: AssetValuationCreate, session: AsyncSession = Depends(get_session)
) -> AssetRead:
    """Records (or corrects) an asset's value as of a date. Re-submitting the
    same date updates that day's value instead of erroring, so users can fix
    a typo without needing a separate edit flow."""
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    upsert_stmt = (
        pg_insert(AssetValuation)
        .values(asset_id=asset_id, value=payload.value, as_of_date=payload.as_of_date)
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={"value": payload.value},
        )
    )
    await session.execute(upsert_stmt)
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    return _to_read(refreshed.scalar_one())


@router.patch("/{asset_id}/valuations/{valuation_id}", response_model=AssetRead)
async def update_asset_valuation(
    asset_id: int,
    valuation_id: int,
    payload: AssetValuationUpdate,
    session: AsyncSession = Depends(get_session),
) -> AssetRead:
    """Исправляет записанную оценку: опечатку в цене или в дате.

    До этого историю можно было только пополнять и удалять по одной точке,
    и ошибку в дате приходилось чинить в два приёма — удалить и записать
    заново. Для ряда, по которому строится кривая капитала, это слишком
    грубо: между удалением и записью история какое-то время неверна.

    День у оценки один: перенос на занятую дату отклоняется, а не
    затирает чужую запись. Две цены на один день — это не вторая оценка, а
    потерянная первая.
    """
    valuation = await session.get(AssetValuation, valuation_id)
    if valuation is None or valuation.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Valuation not found")

    data = payload.model_dump(exclude_unset=True)
    new_date = data.get("as_of_date", valuation.as_of_date)
    if new_date != valuation.as_of_date:
        taken = (
            await session.execute(
                select(AssetValuation.id).where(
                    AssetValuation.asset_id == asset_id,
                    AssetValuation.as_of_date == new_date,
                    AssetValuation.id != valuation_id,
                )
            )
        ).scalar_one_or_none()
        if taken is not None:
            raise HTTPException(status_code=409, detail="A valuation for that date already exists")

    for field, value in data.items():
        setattr(valuation, field, value)
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    return _to_read(refreshed.scalar_one())

@router.get("/{asset_id}/valuations", response_model=list[AssetValuationRead])
async def list_asset_valuations(asset_id: int, session: AsyncSession = Depends(get_session)) -> list[AssetValuation]:
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = await session.execute(
        select(AssetValuation).where(AssetValuation.asset_id == asset_id).order_by(AssetValuation.as_of_date)
    )
    return list(result.scalars().all())


@router.delete("/{asset_id}/valuations/{valuation_id}", status_code=204)
async def delete_asset_valuation(
    asset_id: int, valuation_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    """Убирает одну точку из истории переоценок.

    Нужна ровно для ошибок ввода. Обычная правка цены историю не меняет и не
    должна: актив стоил столько-то тогда и столько-то сейчас, и график
    капитала строится по этим точкам — затирая прошлое, человек переписывал
    бы собственную историю задним числом.

    Последнюю точку удалить можно: тогда текущей становится предыдущая. А
    вот единственную — нет: актив без цены не показать нигде, и вместо
    ошибки ввода получился бы актив-невидимка.
    """
    valuation = await session.get(AssetValuation, valuation_id)
    if valuation is None or valuation.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Valuation not found")

    remaining = (
        await session.execute(
            select(func.count()).select_from(AssetValuation).where(AssetValuation.asset_id == asset_id)
        )
    ).scalar_one()
    if remaining <= 1:
        raise HTTPException(
            status_code=400,
            detail="An asset needs at least one valuation — delete the asset instead",
        )

    await session.delete(valuation)
    await session.commit()


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: int, session: AsyncSession = Depends(get_session)) -> None:
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await session.delete(asset)
    await session.commit()
