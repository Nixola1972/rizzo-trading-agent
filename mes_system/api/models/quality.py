"""Modelli Qualità."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, ARRAY
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from mes_system.db.database import Base


class QualityInspection(Base):
    __tablename__ = "quality_inspections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inventory_items.id"))
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_orders.id"))
    inspection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[str | None] = mapped_column(String(15))
    inspector: Mapped[str | None] = mapped_column(String(50))
    sample_size: Mapped[int | None] = mapped_column(Integer)
    defects_found: Mapped[str | None] = mapped_column(Text)
    measurements: Mapped[dict | None] = mapped_column(JSONB)
    photos: Mapped[list | None] = mapped_column(ARRAY(Text))
    notes: Mapped[str | None] = mapped_column(Text)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class NonConformity(Base):
    __tablename__ = "non_conformities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nc_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_orders.id"))
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inventory_items.id"))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    quantity_affected: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text)
    corrective_action: Mapped[str | None] = mapped_column(Text)
    preventive_action: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    severity: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    created_by: Mapped[str | None] = mapped_column(String(50))
    assigned_to: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
