"""Modelli Prodotti e Distinte Base (BOM)."""

import uuid
from datetime import datetime
from sqlalchemy import String, SmallInteger, Integer, Numeric, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mes_system.db.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(10), default="1.0")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    cycle_time_min: Mapped[int | None] = mapped_column(Integer)
    production_notes: Mapped[str | None] = mapped_column(Text)
    special_instructions: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(50))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[str | None] = mapped_column(String(50))

    bom_lines: Mapped[list["BomLine"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class BomLine(Base):
    __tablename__ = "bom_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200))
    level: Mapped[int] = mapped_column(SmallInteger, default=1)
    phase: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("product_id", "component_id", "reference"),
    )

    product: Mapped["Product"] = relationship(back_populates="bom_lines")
    component: Mapped["Component"] = relationship()

    # Import at runtime to avoid circular
    from .component import Component
