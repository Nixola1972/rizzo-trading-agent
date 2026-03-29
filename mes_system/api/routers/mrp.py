"""Router MRP — Pianificazione Fabbisogni Materiali."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mes_system.db import get_db
from mes_system.api.models.mrp import MrpRun, MrpSuggestion
from mes_system.api.schemas.mrp import (
    MrpRunCreate, MrpRunResponse, MrpSuggestionResponse,
    MrpSuggestionUpdate, MrpCoverageResponse,
)
from mes_system.api.services import mrp_service as svc

router = APIRouter()


@router.post("/run", response_model=MrpRunResponse, status_code=201)
async def run_mrp(data: MrpRunCreate, db: AsyncSession = Depends(get_db)):
    """Esegue un ciclo MRP."""
    try:
        return await svc.run_mrp(db, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=list[MrpRunResponse])
async def list_runs(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MrpRun).order_by(MrpRun.run_date.desc()).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/runs/{run_id}/suggestions", response_model=list[MrpSuggestionResponse])
async def get_suggestions(
    run_id: UUID,
    priority: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(MrpSuggestion).where(MrpSuggestion.mrp_run_id == run_id)
    if priority:
        query = query.where(MrpSuggestion.priority == priority)
    if status:
        query = query.where(MrpSuggestion.status == status)
    query = query.order_by(MrpSuggestion.priority, MrpSuggestion.need_by_date)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.put("/suggestions/{suggestion_id}", response_model=MrpSuggestionResponse)
async def update_suggestion(
    suggestion_id: UUID,
    data: MrpSuggestionUpdate,
    db: AsyncSession = Depends(get_db),
):
    suggestion = await db.get(MrpSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggerimento non trovato")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(suggestion, field, value)
    await db.flush()
    return suggestion


@router.get("/coverage/{product_code}", response_model=MrpCoverageResponse)
async def check_coverage(
    product_code: str,
    quantity: int = Query(1, ge=1),
    horizon_days: int = Query(30, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Verifica copertura materiali per N pezzi di un prodotto."""
    try:
        return await svc.mrp_coverage(db, product_code, quantity, horizon_days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
