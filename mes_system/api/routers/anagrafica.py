"""Router Anagrafica Componenti."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.db import get_db
from mes_system.api.schemas import (
    ComponentCreate, ComponentUpdate, ComponentResponse,
    ComponentListResponse, ComponentSearchParams,
    ComponentSupplierCreate, ComponentSupplierResponse,
    ComponentAlternativeCreate, ComponentAlternativeResponse,
)
from mes_system.api.services import anagrafica_service as svc

router = APIRouter()


@router.get("/", response_model=ComponentListResponse)
async def list_components(
    query: str | None = None,
    category: str | None = None,
    manufacturer: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Lista componenti con ricerca e filtri."""
    params = ComponentSearchParams(
        query=query, category=category, manufacturer=manufacturer,
        page=page, page_size=page_size,
    )
    items, total = await svc.search_components(db, params)
    return ComponentListResponse(
        items=items, total=total, page=page, page_size=page_size,
    )


@router.post("/", response_model=ComponentResponse, status_code=201)
async def create_component(
    data: ComponentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuovo componente con codice interno auto-generato."""
    try:
        component = await svc.create_component(db, data)
        return component
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{component_id}", response_model=ComponentResponse)
async def get_component(
    component_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    component = await svc.get_component(db, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Componente non trovato")
    return component


@router.get("/code/{internal_code}", response_model=ComponentResponse)
async def get_component_by_code(
    internal_code: str,
    db: AsyncSession = Depends(get_db),
):
    component = await svc.get_component_by_code(db, internal_code)
    if not component:
        raise HTTPException(status_code=404, detail="Componente non trovato")
    return component


@router.put("/{component_id}", response_model=ComponentResponse)
async def update_component(
    component_id: UUID,
    data: ComponentUpdate,
    db: AsyncSession = Depends(get_db),
):
    component = await svc.update_component(db, component_id, data)
    if not component:
        raise HTTPException(status_code=404, detail="Componente non trovato")
    return component


@router.post("/{component_id}/suppliers", response_model=ComponentSupplierResponse, status_code=201)
async def add_supplier(
    component_id: UUID,
    data: ComponentSupplierCreate,
    db: AsyncSession = Depends(get_db),
):
    return await svc.add_supplier(db, component_id, data)


@router.post("/{component_id}/alternatives", response_model=ComponentAlternativeResponse, status_code=201)
async def add_alternative(
    component_id: UUID,
    data: ComponentAlternativeCreate,
    db: AsyncSession = Depends(get_db),
):
    return await svc.add_alternative(db, component_id, data)


@router.get("/{component_id}/alternatives", response_model=list[ComponentResponse])
async def get_alternatives(
    component_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_alternatives(db, component_id)
