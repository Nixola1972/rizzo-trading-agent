"""Modelli Ordini di Lavoro (MES)."""

import uuid
from datetime import datetime, date
from sqlalchemy import String, SmallInteger, Integer, Numeric, Text, Boolean, ForeignKey, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mes_system.db.database import Base


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    wo_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    bom_version: Mapped[str | None] = mapped_column(String(10))
    quantity_planned: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_good: Mapped[int] = mapped_column(Integer, default=0)
    quantity_scrap: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    site: Mapped[str] = mapped_column(String(10), default="AL")
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_order: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[int] = mapped_column(SmallInteger, default=5)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    product: Mapped["Product"] = relationship()
    phases: Mapped[list["WoPhase"]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    material_consumption: Mapped[list["WoMaterialConsumption"]] = relationship(back_populates="work_order", cascade="all, delete-orphan")

    from .product import Product


class WoPhase(Base):
    __tablename__ = "wo_phases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    phase_name: Mapped[str] = mapped_column(String(50), nullable=False)
    sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator: Mapped[str | None] = mapped_column(String(50))
    qty_input: Mapped[int | None] = mapped_column(Integer)
    qty_output: Mapped[int | None] = mapped_column(Integer)
    qty_scrap: Mapped[int] = mapped_column(Integer, default=0)
    scrap_reason: Mapped[str | None] = mapped_column(Text)
    setup_time_min: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="phases")


class WoMaterialConsumption(Base):
    __tablename__ = "wo_material_consumption"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"), nullable=False)
    quantity_planned: Mapped[float | None] = mapped_column(Numeric(10, 2))
    quantity_used: Mapped[float | None] = mapped_column(Numeric(10, 2))
    quantity_scrap: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    is_alternative: Mapped[bool] = mapped_column(Boolean, default=False)
    phase: Mapped[str | None] = mapped_column(String(50))
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="material_consumption")
