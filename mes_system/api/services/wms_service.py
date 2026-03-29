"""Servizio WMS — Gestione magazzino, movimenti, stock."""

from uuid import UUID
from datetime import date, datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mes_system.api.models.inventory import InventoryItem, InventoryMovement
from mes_system.api.models.warehouse import Warehouse, WarehouseZone
from mes_system.api.models.component import Component
from mes_system.api.schemas.wms import (
    InventoryItemCreate, MovementCreate, GoodsReceiptCreate,
    StockCheckResponse, StockByZone, TransferRequest,
)
from mes_system.api.services.codifica_service import generate_barcode


async def get_warehouses(db: AsyncSession) -> list[Warehouse]:
    result = await db.execute(
        select(Warehouse).options(selectinload(Warehouse.zones)).order_by(Warehouse.id)
    )
    return list(result.scalars().all())


async def get_zones_by_warehouse(db: AsyncSession, warehouse_id: str) -> list[WarehouseZone]:
    result = await db.execute(
        select(WarehouseZone).where(WarehouseZone.warehouse_id == warehouse_id)
    )
    return list(result.scalars().all())


async def stock_check(db: AsyncSession, component_id: UUID) -> StockCheckResponse:
    """Verifica giacenza di un componente in tutti i magazzini e zone."""
    component = await db.get(Component, component_id)
    if not component:
        raise ValueError(f"Componente {component_id} non trovato")

    result = await db.execute(
        select(
            InventoryItem.zone_id,
            func.sum(InventoryItem.quantity).label("total_qty"),
            func.count(InventoryItem.id).label("items_count"),
        )
        .where(
            InventoryItem.component_id == component_id,
            InventoryItem.status == "AVAILABLE",
            InventoryItem.quantity > 0,
        )
        .group_by(InventoryItem.zone_id)
    )
    rows = result.all()

    stock_by_zone = []
    total = 0.0
    for row in rows:
        zone = await db.get(WarehouseZone, row.zone_id)
        stock_by_zone.append(StockByZone(
            zone_id=row.zone_id,
            zone_name=zone.name if zone else row.zone_id,
            warehouse_id=zone.warehouse_id if zone else "",
            quantity=float(row.total_qty),
            items_count=row.items_count,
        ))
        total += float(row.total_qty)

    return StockCheckResponse(
        component_id=component_id,
        internal_code=component.internal_code,
        description=component.description,
        total_quantity=total,
        stock_by_zone=stock_by_zone,
    )


async def goods_receipt(db: AsyncSession, data: GoodsReceiptCreate) -> list[InventoryItem]:
    """Registra ingresso merce — crea item inventario + movimenti."""
    items_created = []

    for line in data.lines:
        component = await db.get(Component, line.component_id)
        if not component:
            raise ValueError(f"Componente {line.component_id} non trovato")

        barcode = await generate_barcode(db, component.internal_code)

        item = InventoryItem(
            barcode=barcode,
            component_id=line.component_id,
            zone_id=data.zone_id,
            quantity=line.quantity,
            lot_number=line.lot_number,
            supplier_name=line.supplier_name,
            po_reference=line.po_reference,
            receive_date=date.today(),
            weight_g=line.weight_g,
            status="AVAILABLE",
        )
        db.add(item)
        await db.flush()

        movement = InventoryMovement(
            item_id=item.id,
            from_zone=None,
            to_zone=data.zone_id,
            quantity=line.quantity,
            movement_type="RECEIVE",
            reference_type="MANUAL",
            operator=data.operator,
            notes=data.notes,
        )
        db.add(movement)
        items_created.append(item)

    await db.flush()
    return items_created


async def transfer_item(db: AsyncSession, data: TransferRequest) -> InventoryMovement:
    """Trasferisce un item da una zona a un'altra."""
    item = await db.get(InventoryItem, data.item_id)
    if not item:
        raise ValueError(f"Item {data.item_id} non trovato")

    if item.zone_id != data.from_zone:
        raise ValueError(f"Item non si trova in zona {data.from_zone}, è in {item.zone_id}")

    if data.quantity > item.quantity:
        raise ValueError(f"Quantità richiesta ({data.quantity}) > disponibile ({item.quantity})")

    if data.quantity == item.quantity:
        # Sposta tutto l'item
        item.zone_id = data.to_zone
    else:
        # Split: riduce quantità e crea nuovo item nella zona destinazione
        item.quantity -= data.quantity
        new_item = InventoryItem(
            barcode=await generate_barcode(db, "SPLIT"),
            component_id=item.component_id,
            zone_id=data.to_zone,
            quantity=data.quantity,
            quantity_unit=item.quantity_unit,
            lot_number=item.lot_number,
            supplier_name=item.supplier_name,
            po_reference=item.po_reference,
            receive_date=item.receive_date,
            weight_g=None,
            status="AVAILABLE",
        )
        db.add(new_item)

    movement = InventoryMovement(
        item_id=data.item_id,
        from_zone=data.from_zone,
        to_zone=data.to_zone,
        quantity=data.quantity,
        movement_type="TRANSFER",
        operator=data.operator,
        notes=data.notes,
    )
    db.add(movement)
    await db.flush()
    return movement


async def get_inventory_by_zone(db: AsyncSession, zone_id: str) -> list[InventoryItem]:
    result = await db.execute(
        select(InventoryItem)
        .where(
            InventoryItem.zone_id == zone_id,
            InventoryItem.quantity > 0,
        )
        .order_by(InventoryItem.barcode)
    )
    return list(result.scalars().all())


async def get_item_by_barcode(db: AsyncSession, barcode: str) -> InventoryItem | None:
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == barcode)
    )
    return result.scalar_one_or_none()


async def reserve_item(db: AsyncSession, item_id: UUID, work_order_id: UUID) -> InventoryItem:
    """Riserva un item per un ordine di lavoro."""
    item = await db.get(InventoryItem, item_id)
    if not item:
        raise ValueError(f"Item {item_id} non trovato")
    if item.status != "AVAILABLE":
        raise ValueError(f"Item non disponibile, stato: {item.status}")

    item.status = "RESERVED"
    item.reserved_for = work_order_id
    await db.flush()
    return item


async def consume_item(
    db: AsyncSession,
    item_id: UUID,
    quantity: float,
    work_order_id: UUID,
    operator: str,
) -> InventoryMovement:
    """Consuma (scarica) materiale per produzione."""
    item = await db.get(InventoryItem, item_id)
    if not item:
        raise ValueError(f"Item {item_id} non trovato")

    if quantity > item.quantity:
        raise ValueError(f"Quantità richiesta ({quantity}) > disponibile ({item.quantity})")

    item.quantity -= quantity
    if item.quantity == 0:
        item.status = "CONSUMED"

    movement = InventoryMovement(
        item_id=item_id,
        from_zone=item.zone_id,
        to_zone=None,
        quantity=quantity,
        movement_type="CONSUME",
        reference_type="WORK_ORDER",
        reference_id=work_order_id,
        operator=operator,
    )
    db.add(movement)
    await db.flush()
    return movement
