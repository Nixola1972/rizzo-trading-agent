"""Servizio Anagrafica Componenti — CRUD e ricerca."""

from uuid import UUID
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mes_system.api.models.component import Component, ComponentSupplier, ComponentAlternative
from mes_system.api.schemas import (
    ComponentCreate, ComponentUpdate, ComponentSearchParams,
    ComponentSupplierCreate, ComponentAlternativeCreate,
)
from mes_system.api.services.codifica_service import generate_component_code

# Categorie valide
VALID_CATEGORIES = {
    "RES", "CAP", "IC", "DIO", "TRA", "CON",
    "IND", "CRI", "PCB", "MEC", "ETI", "IMB", "ALT",
}


async def create_component(db: AsyncSession, data: ComponentCreate, created_by: str | None = None) -> Component:
    """Crea un nuovo componente con codice interno auto-generato."""
    if data.category.upper() not in VALID_CATEGORIES:
        raise ValueError(f"Categoria non valida: {data.category}. Valide: {VALID_CATEGORIES}")

    internal_code = await generate_component_code(db, data.category, data.subcategory or "GEN")

    component = Component(
        internal_code=internal_code,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(component)
    await db.flush()
    return component


async def get_component(db: AsyncSession, component_id: UUID) -> Component | None:
    result = await db.execute(
        select(Component)
        .options(selectinload(Component.suppliers))
        .where(Component.id == component_id)
    )
    return result.scalar_one_or_none()


async def get_component_by_code(db: AsyncSession, internal_code: str) -> Component | None:
    result = await db.execute(
        select(Component)
        .options(selectinload(Component.suppliers))
        .where(Component.internal_code == internal_code)
    )
    return result.scalar_one_or_none()


async def search_components(db: AsyncSession, params: ComponentSearchParams) -> tuple[list[Component], int]:
    """Cerca componenti con filtri e paginazione."""
    query = select(Component).options(selectinload(Component.suppliers))

    if params.query:
        search = f"%{params.query}%"
        query = query.where(
            or_(
                Component.internal_code.ilike(search),
                Component.mpn.ilike(search),
                Component.description.ilike(search),
                Component.manufacturer.ilike(search),
            )
        )

    if params.category:
        query = query.where(Component.category == params.category.upper())

    if params.manufacturer:
        query = query.where(Component.manufacturer.ilike(f"%{params.manufacturer}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (params.page - 1) * params.page_size
    query = query.offset(offset).limit(params.page_size).order_by(Component.internal_code)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_component(db: AsyncSession, component_id: UUID, data: ComponentUpdate) -> Component | None:
    component = await get_component(db, component_id)
    if not component:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(component, field, value)

    await db.flush()
    return component


async def add_supplier(db: AsyncSession, component_id: UUID, data: ComponentSupplierCreate) -> ComponentSupplier:
    supplier = ComponentSupplier(component_id=component_id, **data.model_dump())
    db.add(supplier)
    await db.flush()
    return supplier


async def add_alternative(db: AsyncSession, component_id: UUID, data: ComponentAlternativeCreate) -> ComponentAlternative:
    alt = ComponentAlternative(component_id=component_id, **data.model_dump())
    db.add(alt)
    await db.flush()
    return alt


async def get_alternatives(db: AsyncSession, component_id: UUID) -> list[Component]:
    """Restituisce i componenti alternativi ordinati per priorità."""
    result = await db.execute(
        select(ComponentAlternative)
        .where(ComponentAlternative.component_id == component_id)
        .order_by(ComponentAlternative.priority)
    )
    alts = result.scalars().all()

    components = []
    for alt in alts:
        comp = await get_component(db, alt.alternative_id)
        if comp:
            components.append(comp)
    return components
