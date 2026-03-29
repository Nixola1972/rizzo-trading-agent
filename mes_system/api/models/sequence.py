"""Modelli Sequenze per codifica automatica."""

from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from mes_system.db.database import Base


class CodeSequence(Base):
    __tablename__ = "code_sequences"

    category: Mapped[str] = mapped_column(String(10), primary_key=True)
    subcategory: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)


class ShipmentSequence(Base):
    __tablename__ = "shipment_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)


class WoSequence(Base):
    __tablename__ = "wo_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)


class NcSequence(Base):
    __tablename__ = "nc_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
