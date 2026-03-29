"""Servizio BOM — Gestione Distinte Base."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mes_system.api.models.product import Product, BomLine
from mes_system.api.models.component import Component
from mes_system.api.schemas.bom import (
    ProductCreate, ProductUpdate, BomLineCreate,
    BomExplosionLine, BomExplosionResponse,
)
from mes_system.api.services.wms_service import stock_check


async def create_product(db: AsyncSession, data: ProductCreate, created_by: str | None = None) -> Product:
    product = Product(created_by=created_by, **data.model_dump())
    db.add(product)
    await db.flush()
    return product


async def get_product(db: AsyncSession, product_id: UUID) -> Product | None:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.bom_lines))
        .where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_code(db: AsyncSession, product_code: str) -> Product | None:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.bom_lines))
        .where(Product.product_code == product_code)
    )
    return result.scalar_one_or_none()


async def list_products(db: AsyncSession, status: str | None = None) -> list[Product]:
    query = select(Product)
    if status:
        query = query.where(Product.status == status)
    query = query.order_by(Product.product_code)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_product(db: AsyncSession, product_id: UUID, data: ProductUpdate) -> Product | None:
    product = await get_product(db, product_id)
    if not product:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.flush()
    return product


async def add_bom_line(db: AsyncSession, product_id: UUID, data: BomLineCreate) -> BomLine:
    line = BomLine(product_id=product_id, **data.model_dump())
    db.add(line)
    await db.flush()
    return line


async def remove_bom_line(db: AsyncSession, line_id: UUID) -> bool:
    line = await db.get(BomLine, line_id)
    if not line:
        return False
    await db.delete(line)
    await db.flush()
    return True


async def explode_bom(
    db: AsyncSession,
    product_code: str,
    quantity: int = 1,
    check_stock: bool = True,
) -> BomExplosionResponse:
    """Esplode la BOM per un prodotto, calcolando fabbisogni e disponibilità."""
    product = await get_product_by_code(db, product_code)
    if not product:
        raise ValueError(f"Prodotto {product_code} non trovato")

    lines = []
    missing_count = 0

    for bom_line in product.bom_lines:
        component = await db.get(Component, bom_line.component_id)
        if not component:
            continue

        qty_total = float(bom_line.quantity) * quantity
        stock_available = 0.0
        stock_status = "UNKNOWN"

        if check_stock:
            try:
                stock = await stock_check(db, component.id)
                stock_available = stock.total_quantity
                if stock_available >= qty_total:
                    stock_status = "OK"
                elif stock_available > 0:
                    stock_status = "LOW"
                else:
                    stock_status = "MISSING"
                    missing_count += 1
            except Exception:
                stock_status = "ERROR"

        # Cerca alternative
        from mes_system.api.models.component import ComponentAlternative
        alt_result = await db.execute(
            select(ComponentAlternative)
            .where(ComponentAlternative.component_id == component.id)
            .order_by(ComponentAlternative.priority)
        )
        alternatives = []
        for alt in alt_result.scalars().all():
            alt_comp = await db.get(Component, alt.alternative_id)
            if alt_comp:
                alternatives.append(alt_comp.internal_code)

        lines.append(BomExplosionLine(
            component_id=component.id,
            component_code=component.internal_code,
            component_description=component.description,
            mpn=component.mpn,
            quantity_per_unit=float(bom_line.quantity),
            quantity_total=qty_total,
            phase=bom_line.phase,
            reference=bom_line.reference,
            alternatives=alternatives,
            stock_available=stock_available,
            stock_status=stock_status,
        ))

    return BomExplosionResponse(
        product_code=product.product_code,
        product_description=product.description,
        version=product.version,
        production_quantity=quantity,
        lines=lines,
        total_components=len(lines),
        missing_components=missing_count,
    )
