"""Router Qualità — Ispezioni e Non Conformità."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.db import get_db
from mes_system.api.schemas.quality import (
    InspectionCreate, InspectionResponse,
    NonConformityCreate, NonConformityUpdate, NonConformityResponse,
    QualityDashboard,
)
from mes_system.api.services import quality_service as svc

router = APIRouter()


@router.post("/inspections", response_model=InspectionResponse, status_code=201)
async def create_inspection(data: InspectionCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_inspection(db, data)


@router.get("/nc", response_model=list[NonConformityResponse])
async def list_nc(
    status: str | None = None,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_non_conformities(db, status, severity)


@router.post("/nc", response_model=NonConformityResponse, status_code=201)
async def create_nc(data: NonConformityCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_non_conformity(db, data)


@router.put("/nc/{nc_id}", response_model=NonConformityResponse)
async def update_nc(nc_id: UUID, data: NonConformityUpdate, db: AsyncSession = Depends(get_db)):
    nc = await svc.update_non_conformity(db, nc_id, data)
    if not nc:
        raise HTTPException(status_code=404, detail="Non conformità non trovata")
    return nc


@router.get("/dashboard", response_model=QualityDashboard)
async def dashboard(db: AsyncSession = Depends(get_db)):
    return await svc.quality_dashboard(db)
