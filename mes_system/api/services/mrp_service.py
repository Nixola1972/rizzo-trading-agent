"""Servizio MRP — Motore di pianificazione fabbisogni materiali.

Logica MRP:
1. Raccogli domanda (ordini di lavoro PLANNED + READY)
2. Esplodi BOM per ogni ordine
3. Calcola fabbisogno lordo per componente
4. Sottrai giacenze disponibili + ordini in arrivo + materiale in transito
5. Considera scorte di sicurezza
6. Genera suggerimenti di acquisto e spedizione
"""

from uuid import UUID
from datetime import datetime, date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.api.models.component import Component, ComponentSupplier
from mes_system.api.models.product import Product, BomLine
from mes_system.api.models.inventory import InventoryItem
from mes_system.api.models.work_order import WorkOrder
from mes_system.api.models.shipment import Shipment, ShipmentItem
from mes_system.api.models.mrp import MrpRun, MrpSuggestion
from mes_system.api.schemas.mrp import MrpRunCreate, MrpCoverageResponse, CoverageItem
from mes_system.config import settings


async def run_mrp(db: AsyncSession, params: MrpRunCreate) -> MrpRun:
    """Esegue un ciclo MRP completo."""
    horizon = params.horizon_days
    horizon_date = date.today() + timedelta(days=horizon)

    # Crea record del run
    mrp_run = MrpRun(
        run_by=params.run_by,
        horizon_days=horizon,
        parameters=params.parameters,
        status="RUNNING",
    )
    db.add(mrp_run)
    await db.flush()

    try:
        # 1. Raccogli domanda: ordini di lavoro pianificati/pronti
        wo_result = await db.execute(
            select(WorkOrder).where(
                WorkOrder.status.in_(["PLANNED", "MATERIAL_CHECK", "READY"]),
                WorkOrder.planned_start <= horizon_date,
            )
        )
        work_orders = list(wo_result.scalars().all())

        # 2. Calcola fabbisogno lordo per componente
        gross_requirements: dict[UUID, float] = {}
        component_need_dates: dict[UUID, date] = {}

        for wo in work_orders:
            bom_result = await db.execute(
                select(BomLine).where(BomLine.product_id == wo.product_id)
            )
            for line in bom_result.scalars().all():
                comp_id = line.component_id
                needed = float(line.quantity) * wo.quantity_planned
                gross_requirements[comp_id] = gross_requirements.get(comp_id, 0) + needed

                # Prendi la data più urgente
                if wo.planned_start:
                    if comp_id not in component_need_dates or wo.planned_start < component_need_dates[comp_id]:
                        component_need_dates[comp_id] = wo.planned_start

        # 3. Per ogni componente, calcola disponibilità e genera suggerimenti
        total_suggestions = 0
        critical_count = 0

        for comp_id, gross_needed in gross_requirements.items():
            component = await db.get(Component, comp_id)
            if not component:
                continue

            # Giacenza disponibile (tutte le zone, status AVAILABLE)
            stock_result = await db.execute(
                select(func.coalesce(func.sum(InventoryItem.quantity), 0))
                .where(
                    InventoryItem.component_id == comp_id,
                    InventoryItem.status == "AVAILABLE",
                )
            )
            available = float(stock_result.scalar() or 0)

            # Materiale in transito
            transit_result = await db.execute(
                select(func.coalesce(func.sum(ShipmentItem.quantity), 0))
                .join(Shipment)
                .join(InventoryItem, ShipmentItem.item_id == InventoryItem.id)
                .where(
                    InventoryItem.component_id == comp_id,
                    Shipment.status.in_(["SHIPPED", "IN_TRANSIT"]),
                )
            )
            in_transit = float(transit_result.scalar() or 0)

            # Scorta di sicurezza (basata su lead time)
            safety_days = settings.mrp_safety_stock_days
            daily_usage = gross_needed / max(horizon, 1)
            safety_stock = daily_usage * safety_days

            # Fabbisogno netto
            net_requirement = gross_needed - available - in_transit + safety_stock
            net_requirement = max(0, net_requirement)

            if net_requirement <= 0:
                continue

            # Arrotonda a MOQ e multiplo d'ordine
            moq = component.moq or 1
            order_multiple = component.order_multiple or 1
            qty_to_order = max(net_requirement, moq)
            if order_multiple > 1:
                qty_to_order = ((qty_to_order + order_multiple - 1) // order_multiple) * order_multiple

            # Calcola data ordine
            lead_time = component.lead_time_days or 14
            need_date = component_need_dates.get(comp_id, horizon_date)
            order_date = need_date - timedelta(days=lead_time)

            # Priorità
            days_until_needed = (need_date - date.today()).days
            if days_until_needed <= 0:
                priority = "CRITICAL"
                critical_count += 1
            elif days_until_needed <= 7:
                priority = "HIGH"
            elif days_until_needed <= 14:
                priority = "MEDIUM"
            else:
                priority = "LOW"

            # Trova fornitore suggerito
            supplier_result = await db.execute(
                select(ComponentSupplier)
                .where(ComponentSupplier.component_id == comp_id)
                .order_by(ComponentSupplier.priority)
                .limit(1)
            )
            supplier = supplier_result.scalar_one_or_none()

            suggestion = MrpSuggestion(
                mrp_run_id=mrp_run.id,
                suggestion_type="PURCHASE",
                component_id=comp_id,
                quantity_needed=gross_needed,
                quantity_available=available + in_transit,
                quantity_to_order=qty_to_order,
                suggested_supplier=supplier.supplier_name if supplier else None,
                order_by_date=order_date if order_date >= date.today() else date.today(),
                need_by_date=need_date,
                priority=priority,
            )
            db.add(suggestion)
            total_suggestions += 1

        # Aggiorna run
        mrp_run.status = "COMPLETED"
        mrp_run.completed_at = datetime.utcnow()
        mrp_run.summary = {
            "work_orders_analyzed": len(work_orders),
            "components_analyzed": len(gross_requirements),
            "suggestions_generated": total_suggestions,
            "critical_items": critical_count,
        }

        await db.flush()
        return mrp_run

    except Exception as e:
        mrp_run.status = "FAILED"
        mrp_run.summary = {"error": str(e)}
        await db.flush()
        raise


async def mrp_coverage(
    db: AsyncSession,
    product_code: str,
    quantity: int,
    horizon_days: int = 30,
) -> MrpCoverageResponse:
    """Verifica copertura materiali per produrre N pezzi di un prodotto."""
    product_result = await db.execute(
        select(Product).where(Product.product_code == product_code)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise ValueError(f"Prodotto {product_code} non trovato")

    bom_result = await db.execute(
        select(BomLine).where(BomLine.product_id == product.id)
    )

    items = []
    critical = 0
    missing = 0
    fully_covered = True

    for line in bom_result.scalars().all():
        component = await db.get(Component, line.component_id)
        if not component:
            continue

        needed = float(line.quantity) * quantity

        # Stock on hand
        stock_result = await db.execute(
            select(func.coalesce(func.sum(InventoryItem.quantity), 0))
            .where(
                InventoryItem.component_id == component.id,
                InventoryItem.status == "AVAILABLE",
            )
        )
        on_hand = float(stock_result.scalar() or 0)

        # In transit
        transit_result = await db.execute(
            select(func.coalesce(func.sum(ShipmentItem.quantity), 0))
            .join(Shipment)
            .join(InventoryItem, ShipmentItem.item_id == InventoryItem.id)
            .where(
                InventoryItem.component_id == component.id,
                Shipment.status.in_(["SHIPPED", "IN_TRANSIT"]),
            )
        )
        in_transit = float(transit_result.scalar() or 0)

        net = needed - on_hand - in_transit
        if net > 0 and on_hand == 0:
            status = "MISSING"
            missing += 1
            fully_covered = False
        elif net > 0:
            status = "PARTIAL"
            critical += 1
            fully_covered = False
        else:
            status = "COVERED"

        # Coverage days
        daily_usage = needed / max(horizon_days, 1)
        coverage_days = int(on_hand / daily_usage) if daily_usage > 0 else None

        items.append(CoverageItem(
            component_id=component.id,
            component_code=component.internal_code,
            description=component.description,
            quantity_needed=needed,
            quantity_on_hand=on_hand,
            quantity_on_order=0,
            quantity_in_transit=in_transit,
            net_requirement=max(0, net),
            coverage_days=coverage_days,
            status=status,
        ))

    return MrpCoverageResponse(
        product_code=product_code,
        quantity=quantity,
        horizon_days=horizon_days,
        coverage_items=items,
        fully_covered=fully_covered,
        critical_count=critical,
        missing_count=missing,
    )
