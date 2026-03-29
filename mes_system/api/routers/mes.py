"""Router MES — Ordini di Lavoro e Produzione."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.db import get_db
from mes_system.api.schemas.mes import (
    WorkOrderCreate, WorkOrderUpdate, WorkOrderResponse,
    WoPhaseResponse, WoPhaseUpdate,
    MaterialConsumptionCreate, MaterialConsumptionResponse,
    ProductionRegistration, ProductionStatusResponse,
)
from mes_system.api.services import mes_service as svc

router = APIRouter()


@router.get("/work-orders", response_model=list[WorkOrderResponse])
async def list_work_orders(
    status: str | None = None,
    site: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_work_orders(db, status, site)


@router.post("/work-orders", response_model=WorkOrderResponse, status_code=201)
async def create_work_order(data: WorkOrderCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.create_work_order(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/work-orders/{wo_id}", response_model=WorkOrderResponse)
async def get_work_order(wo_id: UUID, db: AsyncSession = Depends(get_db)):
    wo = await svc.get_work_order(db, wo_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Ordine di lavoro non trovato")
    return wo


@router.get("/work-orders/code/{wo_code}", response_model=WorkOrderResponse)
async def get_work_order_by_code(wo_code: str, db: AsyncSession = Depends(get_db)):
    wo = await svc.get_work_order_by_code(db, wo_code)
    if not wo:
        raise HTTPException(status_code=404, detail="Ordine di lavoro non trovato")
    return wo


@router.put("/work-orders/{wo_id}", response_model=WorkOrderResponse)
async def update_work_order(wo_id: UUID, data: WorkOrderUpdate, db: AsyncSession = Depends(get_db)):
    wo = await svc.update_work_order(db, wo_id, data)
    if not wo:
        raise HTTPException(status_code=404, detail="Ordine di lavoro non trovato")
    return wo


@router.post("/work-orders/{wo_id}/phases/{phase_id}/start", response_model=WoPhaseResponse)
async def start_phase(wo_id: UUID, phase_id: UUID, operator: str, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.start_phase(db, phase_id, operator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/work-orders/{wo_id}/phases/{phase_id}/complete", response_model=WoPhaseResponse)
async def complete_phase(wo_id: UUID, phase_id: UUID, data: WoPhaseUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.complete_phase(db, phase_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/work-orders/{wo_id}/consume", response_model=MaterialConsumptionResponse, status_code=201)
async def consume_material(wo_id: UUID, data: MaterialConsumptionCreate, db: AsyncSession = Depends(get_db)):
    return await svc.record_material_consumption(db, wo_id, data)


@router.post("/register-production", response_model=WorkOrderResponse)
async def register_production(data: ProductionRegistration, db: AsyncSession = Depends(get_db)):
    """Registra produzione — usato dal Telegram bot e dall'interfaccia web."""
    try:
        return await svc.register_production(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
