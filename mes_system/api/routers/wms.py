"""Router WMS — Magazzino, Inventario, Movimenti."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.db import get_db
from mes_system.api.schemas.wms import (
    WarehouseResponse, WarehouseZoneResponse,
    InventoryItemResponse, MovementResponse,
    GoodsReceiptCreate, GoodsReceiptResponse,
    StockCheckResponse, TransferRequest,
)
from mes_system.api.services import wms_service as svc

router = APIRouter()


@router.get("/warehouses", response_model=list[WarehouseResponse])
async def list_warehouses(db: AsyncSession = Depends(get_db)):
    return await svc.get_warehouses(db)


@router.get("/warehouses/{warehouse_id}/zones", response_model=list[WarehouseZoneResponse])
async def list_zones(warehouse_id: str, db: AsyncSession = Depends(get_db)):
    return await svc.get_zones_by_warehouse(db, warehouse_id)


@router.get("/stock/{component_id}", response_model=StockCheckResponse)
async def check_stock(component_id: UUID, db: AsyncSession = Depends(get_db)):
    """Verifica giacenza componente in tutti i magazzini."""
    try:
        return await svc.stock_check(db, component_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/receipt", response_model=list[InventoryItemResponse], status_code=201)
async def goods_receipt(data: GoodsReceiptCreate, db: AsyncSession = Depends(get_db)):
    """Registra ingresso merce."""
    try:
        return await svc.goods_receipt(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transfer", response_model=MovementResponse)
async def transfer(data: TransferRequest, db: AsyncSession = Depends(get_db)):
    """Trasferimento tra zone."""
    try:
        return await svc.transfer_item(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/zone/{zone_id}/items", response_model=list[InventoryItemResponse])
async def items_by_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    return await svc.get_inventory_by_zone(db, zone_id)


@router.get("/barcode/{barcode}", response_model=InventoryItemResponse)
async def scan_barcode(barcode: str, db: AsyncSession = Depends(get_db)):
    """Cerca item per barcode (scan)."""
    item = await svc.get_item_by_barcode(db, barcode)
    if not item:
        raise HTTPException(status_code=404, detail="Barcode non trovato")
    return item


@router.post("/reserve/{item_id}/{work_order_id}", response_model=InventoryItemResponse)
async def reserve(item_id: UUID, work_order_id: UUID, db: AsyncSession = Depends(get_db)):
    """Riserva item per ordine di lavoro."""
    try:
        return await svc.reserve_item(db, item_id, work_order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
