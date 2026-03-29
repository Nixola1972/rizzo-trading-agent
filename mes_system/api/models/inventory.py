"""Modelli Inventario e Movimenti."""

import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Numeric, Text, ForeignKey, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from mes_system.db.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    barcode: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"), nullable=False)
    zone_id: Mapped[str] = mapped_column(ForeignKey("warehouse_zones.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(10), default="PCS")
    lot_number: Mapped[str | None] = mapped_column(String(50))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    po_reference: Mapped[str | None] = mapped_column(String(50))
    receive_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    weight_g: Mapped[float | None] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    reserved_for: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    component: Mapped["Component"] = relationship()
    zone: Mapped["WarehouseZone"] = relationship()
    movements: Mapped[list["InventoryMovement"]] = relationship(back_populates="item")

    from .component import Component
    from .warehouse import WarehouseZone


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    from_zone: Mapped[str | None] = mapped_column(ForeignKey("warehouse_zones.id"))
    to_zone: Mapped[str | None] = mapped_column(ForeignKey("warehouse_zones.id"))
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    operator: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    item: Mapped["InventoryItem"] = relationship(back_populates="movements")
