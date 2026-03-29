"""Modelli Spedizioni IT↔AL."""

import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Numeric, Text, ForeignKey, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mes_system.db.database import Base


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    shipment_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # IT_TO_AL, AL_TO_IT
    status: Mapped[str] = mapped_column(String(20), default="PREPARING")
    ship_date: Mapped[date | None] = mapped_column(Date)
    expected_arrival: Mapped[date | None] = mapped_column(Date)
    actual_arrival: Mapped[date | None] = mapped_column(Date)
    total_weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 2))
    total_value_eur: Mapped[float | None] = mapped_column(Numeric(12, 2))
    total_packages: Mapped[int | None] = mapped_column(Integer)
    customs_doc_ref: Mapped[str | None] = mapped_column(String(100))
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    carrier: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    items: Mapped[list["ShipmentItem"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")


class ShipmentItem(Base):
    __tablename__ = "shipment_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    customs_value: Mapped[float | None] = mapped_column(Numeric(10, 4))
    customs_weight: Mapped[float | None] = mapped_column(Numeric(10, 4))

    shipment: Mapped["Shipment"] = relationship(back_populates="items")
    item: Mapped["InventoryItem"] = relationship()

    from .inventory import InventoryItem
