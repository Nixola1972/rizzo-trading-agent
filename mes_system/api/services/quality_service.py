"""Servizio Qualità — Ispezioni e Non Conformità."""

from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.api.models.quality import QualityInspection, NonConformity
from mes_system.api.schemas.quality import (
    InspectionCreate, NonConformityCreate, NonConformityUpdate,
    QualityDashboard,
)
from mes_system.api.services.codifica_service import generate_nc_code


async def create_inspection(db: AsyncSession, data: InspectionCreate) -> QualityInspection:
    inspection = QualityInspection(**data.model_dump())
    db.add(inspection)
    await db.flush()
    return inspection


async def create_non_conformity(db: AsyncSession, data: NonConformityCreate) -> NonConformity:
    nc_code = await generate_nc_code(db)
    nc = NonConformity(nc_code=nc_code, **data.model_dump())
    db.add(nc)
    await db.flush()
    return nc


async def update_non_conformity(db: AsyncSession, nc_id: UUID, data: NonConformityUpdate) -> NonConformity | None:
    nc = await db.get(NonConformity, nc_id)
    if not nc:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(nc, field, value)

    if data.status == "CLOSED":
        nc.closed_at = datetime.utcnow()

    await db.flush()
    return nc


async def list_non_conformities(
    db: AsyncSession,
    status: str | None = None,
    severity: str | None = None,
) -> list[NonConformity]:
    query = select(NonConformity)
    if status:
        query = query.where(NonConformity.status == status)
    if severity:
        query = query.where(NonConformity.severity == severity)
    query = query.order_by(NonConformity.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def quality_dashboard(db: AsyncSession) -> QualityDashboard:
    """KPI qualità."""
    # NC aperte
    open_count_result = await db.execute(
        select(func.count(NonConformity.id)).where(
            NonConformity.status.in_(["OPEN", "INVESTIGATING"])
        )
    )
    open_count = open_count_result.scalar() or 0

    # NC per severity
    severity_result = await db.execute(
        select(NonConformity.severity, func.count(NonConformity.id))
        .where(NonConformity.status.in_(["OPEN", "INVESTIGATING"]))
        .group_by(NonConformity.severity)
    )
    nc_by_severity = {row[0]: row[1] for row in severity_result.all()}

    # NC per source
    source_result = await db.execute(
        select(NonConformity.source, func.count(NonConformity.id))
        .where(NonConformity.status.in_(["OPEN", "INVESTIGATING"]))
        .group_by(NonConformity.source)
    )
    nc_by_source = {row[0]: row[1] for row in source_result.all()}

    # Ispezioni oggi
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
    inspections_today_result = await db.execute(
        select(func.count(QualityInspection.id)).where(
            QualityInspection.inspected_at >= today_start
        )
    )
    inspections_today = inspections_today_result.scalar() or 0

    # NC recenti
    recent_result = await db.execute(
        select(NonConformity)
        .order_by(NonConformity.created_at.desc())
        .limit(10)
    )
    recent_nc = list(recent_result.scalars().all())

    return QualityDashboard(
        open_nc_count=open_count,
        nc_by_severity=nc_by_severity,
        nc_by_source=nc_by_source,
        inspections_today=inspections_today,
        first_pass_yield=None,
        top_defective_components=[],
        recent_nc=recent_nc,
    )
