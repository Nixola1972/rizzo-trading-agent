"""Pydantic schemas per Anagrafica Componenti."""

from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field


# === Component Suppliers ===

class ComponentSupplierBase(BaseModel):
    supplier_name: str
    supplier_code: str | None = None
    priority: int = 1
    last_price: float | None = None
    last_price_date: date | None = None
    currency: str = "EUR"
    lead_time_days: int | None = None
    moq: int | None = None
    order_multiple: int | None = None
    notes: str | None = None


class ComponentSupplierCreate(ComponentSupplierBase):
    pass


class ComponentSupplierResponse(ComponentSupplierBase):
    id: UUID
    component_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# === Component Alternatives ===

class ComponentAlternativeBase(BaseModel):
    alternative_id: UUID
    priority: int = 1
    auto_approved: bool = False
    notes: str | None = None


class ComponentAlternativeCreate(ComponentAlternativeBase):
    pass


class ComponentAlternativeResponse(ComponentAlternativeBase):
    component_id: UUID

    model_config = {"from_attributes": True}


# === Components ===

class ComponentBase(BaseModel):
    mpn: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    category: str = Field(..., max_length=10, description="RES, CAP, IC, DIO, TRA, CON, IND, CRI, PCB, MEC, ETI, IMB, ALT")
    subcategory: str | None = Field(None, max_length=20)
    package: str | None = None
    datasheet_url: str | None = None
    # Logistici/doganali
    net_weight_g: float | None = None
    gross_weight_g: float | None = None
    units_per_pkg: int | None = None
    taric_code: str | None = None
    country_origin: str | None = Field(None, max_length=3)
    customs_value: float | None = None
    # Tecnici
    nominal_value: str | None = None
    tolerance: str | None = None
    voltage_rating: str | None = None
    rohs_compliant: bool = True
    msl_level: int | None = None
    temp_range: str | None = None
    # Commerciali
    moq: int = 1
    order_multiple: int = 1
    lead_time_days: int | None = None
    # Qualità
    inspection_level: str = "SAMPLING"
    acceptance_criteria: str | None = None
    inspection_instructions: str | None = None
    # Danea
    danea_code: str | None = None


class ComponentCreate(ComponentBase):
    """Crea componente. Il codice interno viene generato automaticamente."""
    pass


class ComponentUpdate(BaseModel):
    """Aggiornamento parziale componente."""
    mpn: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    package: str | None = None
    datasheet_url: str | None = None
    net_weight_g: float | None = None
    gross_weight_g: float | None = None
    units_per_pkg: int | None = None
    taric_code: str | None = None
    country_origin: str | None = None
    customs_value: float | None = None
    nominal_value: str | None = None
    tolerance: str | None = None
    voltage_rating: str | None = None
    rohs_compliant: bool | None = None
    msl_level: int | None = None
    temp_range: str | None = None
    moq: int | None = None
    order_multiple: int | None = None
    lead_time_days: int | None = None
    inspection_level: str | None = None
    danea_code: str | None = None


class ComponentResponse(ComponentBase):
    id: UUID
    internal_code: str
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    suppliers: list[ComponentSupplierResponse] = []

    model_config = {"from_attributes": True}


class ComponentListResponse(BaseModel):
    items: list[ComponentResponse]
    total: int
    page: int
    page_size: int


class ComponentSearchParams(BaseModel):
    query: str | None = None
    category: str | None = None
    manufacturer: str | None = None
    has_stock: bool | None = None
    page: int = 1
    page_size: int = 50
