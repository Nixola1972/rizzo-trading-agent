"""Servizio Spedizioni IT↔AL — Preparazione, tracking, documenti doganali."""

from uuid import UUID
from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mes_system.api.models.shipment import Shipment, ShipmentItem
from mes_system.api.models.inventory import InventoryItem
from mes_system.api.models.component import Component
from mes_system.api.schemas.shipments import (
    ShipmentCreate, ShipmentUpdate,
    CustomsDocumentData, PackingListLine, PackingListResponse,
)
from mes_system.api.services.codifica_service import generate_shipment_code
from mes_system.config import settings


async def create_shipment(db: AsyncSession, data: ShipmentCreate) -> Shipment:
    """Crea una nuova spedizione e associa gli item."""
    code = await generate_shipment_code(db)

    expected_arrival = None
    if data.ship_date:
        expected_arrival = data.ship_date + timedelta(days=settings.transit_lead_time_days)

    shipment = Shipment(
        shipment_code=code,
        direction=data.direction,
        ship_date=data.ship_date,
        expected_arrival=data.expected_arrival or expected_arrival,
        carrier=data.carrier,
        tracking_number=data.tracking_number,
        notes=data.notes,
        created_by=data.created_by,
    )
    db.add(shipment)
    await db.flush()

    total_weight = 0.0
    total_value = 0.0

    for item_id in data.item_ids:
        item = await db.get(InventoryItem, item_id)
        if not item:
            continue

        component = await db.get(Component, item.component_id)
        customs_weight = float(component.net_weight_g or 0) * float(item.quantity) / 1000 if component else 0
        customs_value = float(component.customs_value or 0) * float(item.quantity) if component else 0

        shipment_item = ShipmentItem(
            shipment_id=shipment.id,
            item_id=item_id,
            quantity=item.quantity,
            customs_weight=customs_weight,
            customs_value=customs_value,
        )
        db.add(shipment_item)

        total_weight += customs_weight
        total_value += customs_value

    shipment.total_weight_kg = total_weight
    shipment.total_value_eur = total_value
    shipment.total_packages = len(data.item_ids)

    await db.flush()
    return shipment


async def get_shipment(db: AsyncSession, shipment_id: UUID) -> Shipment | None:
    result = await db.execute(
        select(Shipment)
        .options(selectinload(Shipment.items))
        .where(Shipment.id == shipment_id)
    )
    return result.scalar_one_or_none()


async def get_shipment_by_code(db: AsyncSession, code: str) -> Shipment | None:
    result = await db.execute(
        select(Shipment)
        .options(selectinload(Shipment.items))
        .where(Shipment.shipment_code == code)
    )
    return result.scalar_one_or_none()


async def list_shipments(
    db: AsyncSession,
    direction: str | None = None,
    status: str | None = None,
) -> list[Shipment]:
    query = select(Shipment).options(selectinload(Shipment.items))
    if direction:
        query = query.where(Shipment.direction == direction)
    if status:
        query = query.where(Shipment.status == status)
    query = query.order_by(Shipment.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_shipment(db: AsyncSession, shipment_id: UUID, data: ShipmentUpdate) -> Shipment | None:
    shipment = await get_shipment(db, shipment_id)
    if not shipment:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(shipment, field, value)

    # Se status = SHIPPED, sposta items a zona transito
    # Se status = DELIVERED, sposta items a zona destinazione
    # (logica semplificata, in produzione va gestita item per item)

    await db.flush()
    return shipment


async def generate_packing_list(db: AsyncSession, shipment_id: UUID) -> PackingListResponse:
    """Genera packing list per una spedizione."""
    shipment = await get_shipment(db, shipment_id)
    if not shipment:
        raise ValueError(f"Spedizione {shipment_id} non trovata")

    lines = []
    totals = {"quantity": 0, "net_weight_g": 0.0, "gross_weight_g": 0.0, "value_eur": 0.0}

    for i, si in enumerate(shipment.items, 1):
        item = await db.get(InventoryItem, si.item_id)
        component = await db.get(Component, item.component_id) if item else None

        net_w = float(component.net_weight_g or 0) * float(si.quantity) if component else 0
        gross_w = float(component.gross_weight_g or 0) * float(si.quantity) if component else 0
        value = float(si.customs_value or 0)

        lines.append(PackingListLine(
            line_number=i,
            barcode=item.barcode if item else "",
            component_code=component.internal_code if component else "",
            description=component.description if component else "",
            mpn=component.mpn if component else "",
            quantity=float(si.quantity),
            net_weight_g=net_w,
            gross_weight_g=gross_w,
            customs_value_eur=value,
            taric_code=component.taric_code if component else None,
            country_origin=component.country_origin if component else None,
        ))

        totals["quantity"] += float(si.quantity)
        totals["net_weight_g"] += net_w
        totals["gross_weight_g"] += gross_w
        totals["value_eur"] += value

    return PackingListResponse(
        shipment_code=shipment.shipment_code,
        date=shipment.ship_date or date.today(),
        lines=lines,
        totals=totals,
    )


async def generate_customs_data(db: AsyncSession, shipment_id: UUID) -> CustomsDocumentData:
    """Genera dati per documenti doganali."""
    shipment = await get_shipment(db, shipment_id)
    if not shipment:
        raise ValueError(f"Spedizione {shipment_id} non trovata")

    packing = await generate_packing_list(db, shipment_id)

    # Raggruppa per codice TARIC
    taric_groups: dict[str, dict] = {}
    for line in packing.lines:
        taric = line.taric_code or "UNKNOWN"
        if taric not in taric_groups:
            taric_groups[taric] = {
                "taric_code": taric,
                "country_origin": line.country_origin,
                "total_quantity": 0,
                "total_weight_g": 0.0,
                "total_value_eur": 0.0,
                "items_count": 0,
            }
        taric_groups[taric]["total_quantity"] += line.quantity
        taric_groups[taric]["total_weight_g"] += line.net_weight_g or 0
        taric_groups[taric]["total_value_eur"] += line.customs_value_eur or 0
        taric_groups[taric]["items_count"] += 1

    sender = settings.company_name if shipment.direction == "IT_TO_AL" else "ItalJobs Sh.p.k."
    receiver = "ItalJobs Sh.p.k." if shipment.direction == "IT_TO_AL" else settings.company_name

    return CustomsDocumentData(
        shipment_code=shipment.shipment_code,
        direction=shipment.direction,
        ship_date=shipment.ship_date,
        sender=sender,
        receiver=receiver,
        items=[],  # simplified, use packing list for full detail
        total_weight_kg=float(shipment.total_weight_kg or 0),
        total_value_eur=float(shipment.total_value_eur or 0),
        total_packages=shipment.total_packages or 0,
        grouped_by_taric=list(taric_groups.values()),
    )
