"""Pydantic schemas per Qualità."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


# === Quality Inspections ===

class InspectionCreate(BaseModel):
    item_id: UUID | None = None
    work_order_id: UUID | None = None
    inspection_type: str  # INCOMING, IN_PROCESS, FINAL
    result: str | None = None  # PASS, FAIL, CONDITIONAL
    inspector: str | None = None
    sample_size: int | None = None
    defects_found: str | None = None
    measurements: dict | None = None
    photos: list[str] | None = None
    notes: str | None = None


class InspectionResponse(InspectionCreate):
    id: UUID
    inspected_at: datetime

    model_config = {"from_attributes": True}


# === Non Conformities ===

class NonConformityCreate(BaseModel):
    source: str  # INCOMING, PRODUCTION, CUSTOMER
    component_id: UUID | None = None
    work_order_id: UUID | None = None
    item_id: UUID | None = None
    supplier_name: str | None = None
    quantity_affected: int | None = None
    description: str
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    created_by: str | None = None
    assigned_to: str | None = None


class NonConformityUpdate(BaseModel):
    root_cause: str | None = None
    corrective_action: str | None = None
    preventive_action: str | None = None
    status: str | None = None
    assigned_to: str | None = None


class NonConformityResponse(BaseModel):
    id: UUID
    nc_code: str
    source: str
    component_id: UUID | None = None
    work_order_id: UUID | None = None
    item_id: UUID | None = None
    supplier_name: str | None = None
    quantity_affected: int | None = None
    description: str
    root_cause: str | None = None
    corrective_action: str | None = None
    preventive_action: str | None = None
    status: str
    severity: str
    created_by: str | None = None
    assigned_to: str | None = None
    created_at: datetime
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


# === Quality Dashboard ===

class QualityDashboard(BaseModel):
    open_nc_count: int
    nc_by_severity: dict  # {CRITICAL: 1, HIGH: 3, ...}
    nc_by_source: dict  # {INCOMING: 5, PRODUCTION: 3, ...}
    inspections_today: int
    first_pass_yield: float | None = None  # percentuale
    top_defective_components: list[dict]
    recent_nc: list[NonConformityResponse]
