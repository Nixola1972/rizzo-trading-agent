"""Servizio di codifica automatica componenti e documenti.

Sistema di codifica:
  Componenti: {PREFIX}-{CATEGORIA}-{SOTTOCATEGORIA}-{SEQUENZIALE:06d}
  Barcode:    {PREFIX}-{CODICE_COMPONENTE}-R{REEL_SEQ:03d}
  Spedizioni: SHIP-{ANNO}-{SEQ:03d}
  Work Order: WO-{ANNO}-{SEQ:04d}
  Non Conf.:  NC-{ANNO}-{SEQ:03d}
"""

from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mes_system.api.models.sequence import CodeSequence, ShipmentSequence, WoSequence, NcSequence
from mes_system.config import settings


async def generate_component_code(
    db: AsyncSession,
    category: str,
    subcategory: str,
) -> str:
    """Genera codice componente: TS-RES-0805-000001"""
    subcategory = subcategory or "GEN"
    category = category.upper()
    subcategory = subcategory.upper()

    # Upsert della sequenza
    result = await db.execute(
        select(CodeSequence).where(
            CodeSequence.category == category,
            CodeSequence.subcategory == subcategory,
        ).with_for_update()
    )
    seq = result.scalar_one_or_none()

    if seq is None:
        seq = CodeSequence(category=category, subcategory=subcategory, last_sequence=0)
        db.add(seq)
        await db.flush()

    seq.last_sequence += 1
    next_val = seq.last_sequence

    return f"{settings.company_prefix}-{category}-{subcategory}-{next_val:06d}"


async def generate_barcode(
    db: AsyncSession,
    component_code: str,
    reel_sequence: int | None = None,
) -> str:
    """Genera barcode per reel/item: TS-RES-0805-000042-R001"""
    if reel_sequence is not None:
        return f"{component_code}-R{reel_sequence:03d}"
    # Auto-increment: conta items esistenti per questo componente
    # Per semplicità usiamo un contatore basato sul timestamp
    ts = int(datetime.utcnow().timestamp()) % 100000
    return f"{component_code}-R{ts:05d}"


async def generate_shipment_code(db: AsyncSession) -> str:
    """Genera codice spedizione: SHIP-2026-001"""
    year = datetime.utcnow().year

    result = await db.execute(
        select(ShipmentSequence).where(
            ShipmentSequence.year == year
        ).with_for_update()
    )
    seq = result.scalar_one_or_none()

    if seq is None:
        seq = ShipmentSequence(year=year, last_sequence=0)
        db.add(seq)
        await db.flush()

    seq.last_sequence += 1
    return f"SHIP-{year}-{seq.last_sequence:03d}"


async def generate_wo_code(db: AsyncSession) -> str:
    """Genera codice ordine di lavoro: WO-2026-0042"""
    year = datetime.utcnow().year

    result = await db.execute(
        select(WoSequence).where(WoSequence.year == year).with_for_update()
    )
    seq = result.scalar_one_or_none()

    if seq is None:
        seq = WoSequence(year=year, last_sequence=0)
        db.add(seq)
        await db.flush()

    seq.last_sequence += 1
    return f"WO-{year}-{seq.last_sequence:04d}"


async def generate_nc_code(db: AsyncSession) -> str:
    """Genera codice non conformità: NC-2026-001"""
    year = datetime.utcnow().year

    result = await db.execute(
        select(NcSequence).where(NcSequence.year == year).with_for_update()
    )
    seq = result.scalar_one_or_none()

    if seq is None:
        seq = NcSequence(year=year, last_sequence=0)
        db.add(seq)
        await db.flush()

    seq.last_sequence += 1
    return f"NC-{year}-{seq.last_sequence:03d}"
