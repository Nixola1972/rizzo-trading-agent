"""Router BOM — Distinte Base."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.db import get_db
from mes_system.api.schemas.bom import (
    ProductCreate, ProductUpdate, ProductResponse, ProductWithBomResponse,
    BomLineCreate, BomLineResponse, BomExplosionResponse,
)
from mes_system.api.services import bom_service as svc

router = APIRouter()


@router.get("/products", response_model=list[ProductResponse])
async def list_products(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_products(db, status)


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_product(db, data)


@router.get("/products/{product_id}", response_model=ProductWithBomResponse)
async def get_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await svc.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return product


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: UUID, data: ProductUpdate, db: AsyncSession = Depends(get_db)):
    product = await svc.update_product(db, product_id, data)
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return product


@router.post("/products/{product_id}/lines", response_model=BomLineResponse, status_code=201)
async def add_bom_line(product_id: UUID, data: BomLineCreate, db: AsyncSession = Depends(get_db)):
    return await svc.add_bom_line(db, product_id, data)


@router.delete("/lines/{line_id}", status_code=204)
async def remove_bom_line(line_id: UUID, db: AsyncSession = Depends(get_db)):
    if not await svc.remove_bom_line(db, line_id):
        raise HTTPException(status_code=404, detail="Riga BOM non trovata")


@router.get("/explode/{product_code}", response_model=BomExplosionResponse)
async def explode_bom(
    product_code: str,
    quantity: int = Query(1, ge=1),
    check_stock: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Esplode la BOM con verifica disponibilità stock."""
    try:
        return await svc.explode_bom(db, product_code, quantity, check_stock)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
