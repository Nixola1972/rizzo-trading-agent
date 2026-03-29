"""Pydantic schemas per Spedizioni IT↔AL."""

from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel


# === Shipments ===

class ShipmentBase(BaseModel):
    direction: str  # IT_TO_AL, AL_TO_IT
    ship_date: date | None = None
    expected_arrival: date | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    notes: str | None = None


class ShipmentCreate(ShipmentBase):
    """Il codice spedizione viene generato automaticamente."""
    created_by: str | None = None
    item_ids: list[UUID] = []  # inventory items da spedire


class ShipmentUpdate(BaseModel):
    status: str | None = None
    ship_date: date | None = None
    expected_arrival: date | None = None
    actual_arrival: date | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    customs_doc_ref: str | None = None
    notes: str | None = None


class ShipmentItemResponse(BaseModel):
    id: UUID
    item_id: UUID
    barcode: str | None = None
    component_code: str | None = None
    component_description: str | None = None
    quantity: float
    customs_value: float | None = None
    customs_weight: float | None = None

    model_config = {"from_attributes": True}


class ShipmentResponse(ShipmentBase):
    id: UUID
    shipment_code: str
    status: str
    actual_arrival: date | None = None
    total_weight_kg: float | None = None
    total_value_eur: float | None = None
    total_packages: int | None = None
    customs_doc_ref: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ShipmentItemResponse] = []

    model_config = {"from_attributes": True}


# === Customs Documents ===

class CustomsDocumentData(BaseModel):
    shipment_code: str
    direction: str
    ship_date: date | None = None
    sender: str
    receiver: str
    items: list[ShipmentItemResponse]
    total_weight_kg: float
    total_value_eur: float
    total_packages: int
    grouped_by_taric: list[dict]  # raggruppamento per codice TARIC


# === Packing List ===

class PackingListLine(BaseModel):
    line_number: int
    barcode: str
    component_code: str
    description: str | None = None
    mpn: str | None = None
    quantity: float
    net_weight_g: float | None = None
    gross_weight_g: float | None = None
    customs_value_eur: float | None = None
    taric_code: str | None = None
    country_origin: str | None = None


class PackingListResponse(BaseModel):
    shipment_code: str
    date: date
    lines: list[PackingListLine]
    totals: dict
