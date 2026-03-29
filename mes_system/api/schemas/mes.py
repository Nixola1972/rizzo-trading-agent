"""Pydantic schemas per MES (Manufacturing Execution System)."""

from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel


# === Work Orders ===

class WorkOrderBase(BaseModel):
    product_id: UUID
    quantity_planned: int
    site: str = "AL"
    planned_start: date | None = None
    planned_end: date | None = None
    customer_order: str | None = None
    priority: int = 5
    notes: str | None = None


class WorkOrderCreate(WorkOrderBase):
    """Il codice WO viene generato automaticamente."""
    created_by: str | None = None


class WorkOrderUpdate(BaseModel):
    status: str | None = None
    quantity_good: int | None = None
    quantity_scrap: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    priority: int | None = None
    notes: str | None = None


class WorkOrderResponse(WorkOrderBase):
    id: UUID
    wo_code: str
    bom_version: str | None = None
    quantity_good: int
    quantity_scrap: int
    status: str
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    product_code: str | None = None
    product_description: str | None = None
    progress_pct: float = 0.0

    model_config = {"from_attributes": True}


# === WO Phases ===

class WoPhaseBase(BaseModel):
    phase_name: str
    sequence: int


class WoPhaseCreate(WoPhaseBase):
    pass


class WoPhaseUpdate(BaseModel):
    status: str | None = None
    operator: str | None = None
    qty_input: int | None = None
    qty_output: int | None = None
    qty_scrap: int | None = None
    scrap_reason: str | None = None
    setup_time_min: int | None = None
    notes: str | None = None


class WoPhaseResponse(WoPhaseBase):
    id: UUID
    work_order_id: UUID
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    operator: str | None = None
    qty_input: int | None = None
    qty_output: int | None = None
    qty_scrap: int
    scrap_reason: str | None = None
    setup_time_min: int | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


# === Material Consumption ===

class MaterialConsumptionCreate(BaseModel):
    item_id: UUID  # barcode/reel specifico
    component_id: UUID
    quantity_used: float
    quantity_scrap: float = 0
    is_alternative: bool = False
    phase: str | None = None


class MaterialConsumptionResponse(MaterialConsumptionCreate):
    id: UUID
    work_order_id: UUID
    quantity_planned: float | None = None
    consumed_at: datetime

    model_config = {"from_attributes": True}


# === Production Registration (per Telegram bot) ===

class ProductionRegistration(BaseModel):
    """Schema per registrazione produzione via Telegram/vocale."""
    work_order_code: str
    phase_name: str | None = None
    quantity_good: int
    quantity_scrap: int = 0
    scrap_reason: str | None = None
    operator: str
    notes: str | None = None


class ProductionRegistrationConfirm(BaseModel):
    """Conferma dopo interpretazione vocale."""
    registration: ProductionRegistration
    confidence: float  # 0-1, quanto è sicuro il riconoscimento
    original_text: str  # testo trascritto dal vocale
    needs_confirmation: bool = True


# === Production Status ===

class ProductionStatusResponse(BaseModel):
    work_order: WorkOrderResponse
    phases: list[WoPhaseResponse]
    materials_consumed: list[MaterialConsumptionResponse]
    yield_rate: float | None = None
    time_elapsed_min: int | None = None
    time_remaining_min: int | None = None
