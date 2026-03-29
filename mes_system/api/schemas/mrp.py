"""Pydantic schemas per MRP (Material Requirements Planning)."""

from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel


# === MRP Run ===

class MrpRunCreate(BaseModel):
    horizon_days: int = 30
    run_by: str | None = None
    parameters: dict | None = None


class MrpRunResponse(BaseModel):
    id: UUID
    run_date: datetime
    run_by: str | None = None
    horizon_days: int
    status: str
    completed_at: datetime | None = None
    summary: dict | None = None
    suggestions_count: int = 0

    model_config = {"from_attributes": True}


# === MRP Suggestions ===

class MrpSuggestionResponse(BaseModel):
    id: UUID
    mrp_run_id: UUID
    suggestion_type: str  # PURCHASE, SHIP_TO_AL, ALERT
    component_id: UUID
    component_code: str | None = None
    component_description: str | None = None
    quantity_needed: float
    quantity_available: float
    quantity_to_order: float
    suggested_supplier: str | None = None
    order_by_date: date | None = None
    need_by_date: date | None = None
    priority: str
    status: str
    notes: str | None = None

    model_config = {"from_attributes": True}


class MrpSuggestionUpdate(BaseModel):
    status: str  # OPEN, ACCEPTED, ORDERED, DISMISSED
    notes: str | None = None


# === MRP Coverage ===

class CoverageItem(BaseModel):
    component_id: UUID
    component_code: str
    description: str | None = None
    quantity_needed: float
    quantity_on_hand: float
    quantity_on_order: float
    quantity_in_transit: float
    net_requirement: float
    coverage_days: int | None = None
    status: str  # COVERED, PARTIAL, CRITICAL, MISSING
    alternatives_available: float = 0


class MrpCoverageResponse(BaseModel):
    product_code: str
    quantity: int
    horizon_days: int
    coverage_items: list[CoverageItem]
    fully_covered: bool
    critical_count: int
    missing_count: int


# === MRP Dashboard ===

class MrpDashboard(BaseModel):
    active_work_orders: int
    critical_components: int
    total_requirement_value: float
    pending_purchases: int
    next_shipments: list[dict]
    coverage_summary: dict
