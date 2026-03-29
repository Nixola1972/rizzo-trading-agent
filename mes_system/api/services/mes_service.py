"""Servizio MES — Gestione ordini di lavoro e produzione."""

from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mes_system.api.models.work_order import WorkOrder, WoPhase, WoMaterialConsumption
from mes_system.api.models.product import Product
from mes_system.api.schemas.mes import (
    WorkOrderCreate, WorkOrderUpdate, WoPhaseUpdate,
    MaterialConsumptionCreate, ProductionRegistration,
)
from mes_system.api.services.codifica_service import generate_wo_code

# Fasi standard di produzione SMD/THT
DEFAULT_PHASES = [
    ("SERIGRAFIA", 1),
    ("PICK_PLACE", 2),
    ("REFLOW", 3),
    ("AOI", 4),
    ("WAVE", 5),
    ("TEST", 6),
    ("ASSEMBLY", 7),
]


async def create_work_order(db: AsyncSession, data: WorkOrderCreate) -> WorkOrder:
    """Crea un ordine di lavoro con fasi standard."""
    wo_code = await generate_wo_code(db)

    # Verifica prodotto e prendi versione BOM
    product = await db.get(Product, data.product_id)
    if not product:
        raise ValueError(f"Prodotto {data.product_id} non trovato")

    wo = WorkOrder(
        wo_code=wo_code,
        bom_version=product.version,
        **data.model_dump(),
    )
    db.add(wo)
    await db.flush()

    # Crea fasi standard
    for phase_name, seq in DEFAULT_PHASES:
        phase = WoPhase(
            work_order_id=wo.id,
            phase_name=phase_name,
            sequence=seq,
        )
        db.add(phase)

    await db.flush()
    return wo


async def get_work_order(db: AsyncSession, wo_id: UUID) -> WorkOrder | None:
    result = await db.execute(
        select(WorkOrder)
        .options(
            selectinload(WorkOrder.phases),
            selectinload(WorkOrder.material_consumption),
        )
        .where(WorkOrder.id == wo_id)
    )
    return result.scalar_one_or_none()


async def get_work_order_by_code(db: AsyncSession, wo_code: str) -> WorkOrder | None:
    result = await db.execute(
        select(WorkOrder)
        .options(
            selectinload(WorkOrder.phases),
            selectinload(WorkOrder.material_consumption),
        )
        .where(WorkOrder.wo_code == wo_code)
    )
    return result.scalar_one_or_none()


async def list_work_orders(
    db: AsyncSession,
    status: str | None = None,
    site: str | None = None,
) -> list[WorkOrder]:
    query = select(WorkOrder)
    if status:
        query = query.where(WorkOrder.status == status)
    if site:
        query = query.where(WorkOrder.site == site)
    query = query.order_by(WorkOrder.priority, WorkOrder.planned_start)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_work_order(db: AsyncSession, wo_id: UUID, data: WorkOrderUpdate) -> WorkOrder | None:
    wo = await get_work_order(db, wo_id)
    if not wo:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(wo, field, value)

    # Auto-set timestamps
    if data.status == "IN_PROGRESS" and not wo.actual_start:
        wo.actual_start = datetime.utcnow()
    elif data.status in ("COMPLETED", "CLOSED") and not wo.actual_end:
        wo.actual_end = datetime.utcnow()

    await db.flush()
    return wo


async def start_phase(db: AsyncSession, phase_id: UUID, operator: str) -> WoPhase:
    """Avvia una fase di produzione."""
    phase = await db.get(WoPhase, phase_id)
    if not phase:
        raise ValueError(f"Fase {phase_id} non trovata")

    phase.status = "IN_PROGRESS"
    phase.started_at = datetime.utcnow()
    phase.operator = operator
    await db.flush()

    # Se è la prima fase, aggiorna anche il WO
    wo = await get_work_order(db, phase.work_order_id)
    if wo and wo.status in ("PLANNED", "MATERIAL_CHECK", "READY"):
        wo.status = "IN_PROGRESS"
        if not wo.actual_start:
            wo.actual_start = datetime.utcnow()
        await db.flush()

    return phase


async def complete_phase(db: AsyncSession, phase_id: UUID, data: WoPhaseUpdate) -> WoPhase:
    """Completa una fase di produzione."""
    phase = await db.get(WoPhase, phase_id)
    if not phase:
        raise ValueError(f"Fase {phase_id} non trovata")

    phase.status = "COMPLETED"
    phase.completed_at = datetime.utcnow()

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(phase, field, value)

    await db.flush()
    return phase


async def register_production(db: AsyncSession, data: ProductionRegistration) -> WorkOrder:
    """Registra produzione — usato dal bot Telegram e dall'interfaccia web.

    Aggiorna quantità buone/scarti dell'ordine di lavoro e
    completa la fase se specificata.
    """
    wo = await get_work_order_by_code(db, data.work_order_code)
    if not wo:
        raise ValueError(f"Ordine di lavoro {data.work_order_code} non trovato")

    wo.quantity_good += data.quantity_good
    wo.quantity_scrap += data.quantity_scrap

    # Se specificata una fase, aggiornala
    if data.phase_name and wo.phases:
        for phase in wo.phases:
            if phase.phase_name == data.phase_name:
                phase.qty_output = (phase.qty_output or 0) + data.quantity_good
                phase.qty_scrap = (phase.qty_scrap or 0) + data.quantity_scrap
                if data.scrap_reason:
                    phase.scrap_reason = data.scrap_reason
                phase.operator = data.operator
                break

    # Controlla se completato
    if wo.quantity_good + wo.quantity_scrap >= wo.quantity_planned:
        wo.status = "COMPLETED"
        wo.actual_end = datetime.utcnow()

    await db.flush()
    return wo


async def record_material_consumption(
    db: AsyncSession,
    wo_id: UUID,
    data: MaterialConsumptionCreate,
) -> WoMaterialConsumption:
    """Registra consumo materiale per un ordine di lavoro."""
    consumption = WoMaterialConsumption(
        work_order_id=wo_id,
        **data.model_dump(),
    )
    db.add(consumption)
    await db.flush()
    return consumption
