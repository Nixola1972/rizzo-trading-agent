"""Modelli MRP (Material Requirements Planning)."""

import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Numeric, Text, ForeignKey, DateTime, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mes_system.db.database import Base


class MrpRun(Base):
    __tablename__ = "mrp_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    run_by: Mapped[str | None] = mapped_column(String(50))
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict | None] = mapped_column(JSONB)

    suggestions: Mapped[list["MrpSuggestion"]] = relationship(back_populates="mrp_run", cascade="all, delete-orphan")


class MrpSuggestion(Base):
    __tablename__ = "mrp_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mrp_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mrp_runs.id", ondelete="CASCADE"), nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"), nullable=False)
    quantity_needed: Mapped[float | None] = mapped_column(Numeric(12, 2))
    quantity_available: Mapped[float | None] = mapped_column(Numeric(12, 2))
    quantity_to_order: Mapped[float | None] = mapped_column(Numeric(12, 2))
    suggested_supplier: Mapped[str | None] = mapped_column(String(200))
    order_by_date: Mapped[date | None] = mapped_column(Date)
    need_by_date: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    mrp_run: Mapped["MrpRun"] = relationship(back_populates="suggestions")
    component: Mapped["Component"] = relationship()

    from .component import Component
