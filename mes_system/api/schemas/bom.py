"""Pydantic schemas per BOM (Distinte Base)."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


# === Products ===

class ProductBase(BaseModel):
    product_code: str
    description: str | None = None
    version: str = "1.0"
    cycle_time_min: int | None = None
    production_notes: str | None = None
    special_instructions: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    description: str | None = None
    version: str | None = None
    status: str | None = None
    cycle_time_min: int | None = None
    production_notes: str | None = None
    special_instructions: str | None = None


class ProductResponse(ProductBase):
    id: UUID
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None

    model_config = {"from_attributes": True}


# === BOM Lines ===

class BomLineBase(BaseModel):
    component_id: UUID
    quantity: float
    reference: str | None = None
    level: int = 1
    phase: str | None = None
    notes: str | None = None


class BomLineCreate(BomLineBase):
    pass


class BomLineResponse(BomLineBase):
    id: UUID
    product_id: UUID
    component_code: str | None = None
    component_description: str | None = None
    component_mpn: str | None = None

    model_config = {"from_attributes": True}


# === BOM Explosion ===

class BomExplosionLine(BaseModel):
    component_id: UUID
    component_code: str
    component_description: str | None = None
    mpn: str | None = None
    quantity_per_unit: float
    quantity_total: float  # per_unit * production_qty
    phase: str | None = None
    reference: str | None = None
    alternatives: list[str] = []  # codici alternativi
    stock_available: float = 0
    stock_status: str = "UNKNOWN"  # OK, LOW, MISSING


class BomExplosionResponse(BaseModel):
    product_code: str
    product_description: str | None = None
    version: str
    production_quantity: int
    lines: list[BomExplosionLine]
    total_components: int
    missing_components: int


# === BOM with full details ===

class ProductWithBomResponse(ProductResponse):
    bom_lines: list[BomLineResponse] = []
