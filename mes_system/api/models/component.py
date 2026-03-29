"""Modelli Anagrafica Componenti."""

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, SmallInteger, Integer, Numeric, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mes_system.db.database import Base


class Component(Base):
    __tablename__ = "components"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    internal_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    mpn: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(10), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(20))
    package: Mapped[str | None] = mapped_column(String(30))
    datasheet_url: Mapped[str | None] = mapped_column(Text)

    # Dati logistici/doganali
    net_weight_g: Mapped[float | None] = mapped_column(Numeric(10, 4))
    gross_weight_g: Mapped[float | None] = mapped_column(Numeric(10, 4))
    units_per_pkg: Mapped[int | None] = mapped_column(Integer)
    taric_code: Mapped[str | None] = mapped_column(String(20))
    country_origin: Mapped[str | None] = mapped_column(String(3))
    customs_value: Mapped[float | None] = mapped_column(Numeric(10, 4))

    # Dati tecnici
    nominal_value: Mapped[str | None] = mapped_column(String(50))
    tolerance: Mapped[str | None] = mapped_column(String(20))
    voltage_rating: Mapped[str | None] = mapped_column(String(20))
    rohs_compliant: Mapped[bool] = mapped_column(Boolean, default=True)
    msl_level: Mapped[int | None] = mapped_column(SmallInteger)
    temp_range: Mapped[str | None] = mapped_column(String(30))

    # Dati commerciali
    moq: Mapped[int] = mapped_column(Integer, default=1)
    order_multiple: Mapped[int] = mapped_column(Integer, default=1)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)

    # Dati qualità
    inspection_level: Mapped[str] = mapped_column(String(20), default="SAMPLING")
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    inspection_instructions: Mapped[str | None] = mapped_column(Text)

    # Sync Danea
    danea_code: Mapped[str | None] = mapped_column(String(50))

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[str | None] = mapped_column(String(50))

    # Relationships
    suppliers: Mapped[list["ComponentSupplier"]] = relationship(back_populates="component", cascade="all, delete-orphan")
    alternatives: Mapped[list["ComponentAlternative"]] = relationship(
        foreign_keys="ComponentAlternative.component_id",
        back_populates="component",
        cascade="all, delete-orphan",
    )


class ComponentSupplier(Base):
    __tablename__ = "component_suppliers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_code: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[int] = mapped_column(SmallInteger, default=1)
    last_price: Mapped[float | None] = mapped_column(Numeric(12, 4))
    last_price_date: Mapped[datetime | None] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    moq: Mapped[int | None] = mapped_column(Integer)
    order_multiple: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    component: Mapped["Component"] = relationship(back_populates="suppliers")


class ComponentAlternative(Base):
    __tablename__ = "component_alternatives"

    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)
    alternative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)
    priority: Mapped[int] = mapped_column(SmallInteger, default=1)
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    component: Mapped["Component"] = relationship(foreign_keys=[component_id], back_populates="alternatives")
    alternative: Mapped["Component"] = relationship(foreign_keys=[alternative_id])
