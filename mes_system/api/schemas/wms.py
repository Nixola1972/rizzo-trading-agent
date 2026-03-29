"""Pydantic schemas per WMS (Warehouse Management)."""

from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field


# === Warehouses & Zones ===

class WarehouseResponse(BaseModel):
    id: str
    name: str
    location: str | None = None
    country: str | None = None
    is_active: bool = True
    zones: list["WarehouseZoneResponse"] = []

    model_config = {"from_attributes": True}


class WarehouseZoneResponse(BaseModel):
    id: str
    warehouse_id: str
    name: str
    zone_type: str
    is_active: bool = True

    model_config = {"from_attributes": True}


# === Inventory Items ===

class InventoryItemBase(BaseModel):
    component_id: UUID
    zone_id: str
    quantity: float
    quantity_unit: str = "PCS"
    lot_number: str | None = None
    supplier_name: str | None = None
    po_reference: str | None = None
    receive_date: date | None = None
    expiry_date: date | None = None
    weight_g: float | None = None


class InventoryItemCreate(InventoryItemBase):
    """Il barcode viene generato automaticamente."""
    pass


class InventoryItemResponse(InventoryItemBase):
    id: UUID
    barcode: str
    status: str
    reserved_for: UUID | None = None
    created_at: datetime
    updated_at: datetime
    component_code: str | None = None
    component_description: str | None = None
    zone_name: str | None = None

    model_config = {"from_attributes": True}


# === Inventory Movements ===

class MovementCreate(BaseModel):
    item_id: UUID
    from_zone: str | None = None
    to_zone: str | None = None
    quantity: float
    movement_type: str = Field(..., description="RECEIVE, TRANSFER, SHIP, CONSUME, RETURN, SCRAP, ADJUST")
    reference_type: str | None = None
    reference_id: UUID | None = None
    operator: str | None = None
    notes: str | None = None


class MovementResponse(MovementCreate):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# === Stock Check ===

class StockByZone(BaseModel):
    zone_id: str
    zone_name: str
    warehouse_id: str
    quantity: float
    items_count: int


class StockCheckResponse(BaseModel):
    component_id: UUID
    internal_code: str
    description: str | None = None
    total_quantity: float
    stock_by_zone: list[StockByZone]


# === Goods Receipt ===

class GoodsReceiptLine(BaseModel):
    component_id: UUID
    quantity: float
    lot_number: str | None = None
    supplier_name: str | None = None
    po_reference: str | None = None
    weight_g: float | None = None


class GoodsReceiptCreate(BaseModel):
    zone_id: str = "IT-INCOMING"
    operator: str
    lines: list[GoodsReceiptLine]
    notes: str | None = None


class GoodsReceiptResponse(BaseModel):
    items_created: list[InventoryItemResponse]
    movements: list[MovementResponse]


# === Transfer ===

class TransferRequest(BaseModel):
    item_id: UUID
    from_zone: str
    to_zone: str
    quantity: float
    operator: str
    notes: str | None = None


# === Material Availability for Albania ===

class MaterialAvailabilityItem(BaseModel):
    component_code: str
    component_description: str | None = None
    quantity_needed: float
    quantity_available_it: float
    quantity_in_transit: float
    quantity_available_al: float
    status: str  # READY, PARTIAL, MISSING
    expected_arrival: date | None = None


class MaterialAvailabilityResponse(BaseModel):
    work_order_code: str | None = None
    items: list[MaterialAvailabilityItem]
    overall_status: str
