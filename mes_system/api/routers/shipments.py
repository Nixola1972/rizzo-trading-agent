"""Router Spedizioni IT↔AL."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.db import get_db
from mes_system.api.schemas.shipments import (
    ShipmentCreate, ShipmentUpdate, ShipmentResponse,
    PackingListResponse, CustomsDocumentData,
)
from mes_system.api.services import shipment_service as svc

router = APIRouter()


@router.get("/", response_model=list[ShipmentResponse])
async def list_shipments(
    direction: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_shipments(db, direction, status)


@router.post("/", response_model=ShipmentResponse, status_code=201)
async def create_shipment(data: ShipmentCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_shipment(db, data)


@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(shipment_id: UUID, db: AsyncSession = Depends(get_db)):
    shipment = await svc.get_shipment(db, shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Spedizione non trovata")
    return shipment


@router.get("/code/{code}", response_model=ShipmentResponse)
async def get_shipment_by_code(code: str, db: AsyncSession = Depends(get_db)):
    shipment = await svc.get_shipment_by_code(db, code)
    if not shipment:
        raise HTTPException(status_code=404, detail="Spedizione non trovata")
    return shipment


@router.put("/{shipment_id}", response_model=ShipmentResponse)
async def update_shipment(shipment_id: UUID, data: ShipmentUpdate, db: AsyncSession = Depends(get_db)):
    shipment = await svc.update_shipment(db, shipment_id, data)
    if not shipment:
        raise HTTPException(status_code=404, detail="Spedizione non trovata")
    return shipment


@router.get("/{shipment_id}/packing-list", response_model=PackingListResponse)
async def packing_list(shipment_id: UUID, db: AsyncSession = Depends(get_db)):
    """Genera packing list per la spedizione."""
    try:
        return await svc.generate_packing_list(db, shipment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{shipment_id}/customs", response_model=CustomsDocumentData)
async def customs_documents(shipment_id: UUID, db: AsyncSession = Depends(get_db)):
    """Genera dati documenti doganali."""
    try:
        return await svc.generate_customs_data(db, shipment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
