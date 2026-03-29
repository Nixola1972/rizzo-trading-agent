"""Modelli Magazzini e Zone."""

from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mes_system.db.database import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    zones: Mapped[list["WarehouseZone"]] = relationship(back_populates="warehouse", cascade="all, delete-orphan")


class WarehouseZone(Base):
    __tablename__ = "warehouse_zones"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    warehouse_id: Mapped[str] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    warehouse: Mapped["Warehouse"] = relationship(back_populates="zones")
