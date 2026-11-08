"""Persistence: analysis runs, evidence and the prediction log.

Plain SQLAlchemy models; SQLite by default, PostgreSQL by changing SRP_DATABASE_URL.
"""

from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(40), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), index=True)  # queued | running | completed | partial | failed
    requested_at: Mapped[str] = mapped_column(String(40), index=True)
    completed_at: Mapped[str | None] = mapped_column(String(40))
    market_data_as_of: Mapped[str | None] = mapped_column(String(40))
    data_status: Mapped[str | None] = mapped_column(String(16))
    snapshot_id: Mapped[str | None] = mapped_column(String(40))
    deterministic_hash: Mapped[str | None] = mapped_column(String(64))
    versions: Mapped[dict] = mapped_column(JSON, default=dict)
    activity: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict | None] = mapped_column(JSON)
    report: Mapped[dict | None] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)


class EvidenceRow(Base):
    __tablename__ = "evidence"

    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    instrument_id: Mapped[str] = mapped_column(String(40), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    provider_symbol: Mapped[str] = mapped_column(String(32))
    horizon: Mapped[str] = mapped_column(String(10))
    rating: Mapped[str] = mapped_column(String(20))
    issued_at: Mapped[str] = mapped_column(String(40))
    start_date: Mapped[str] = mapped_column(String(10))
    start_close: Mapped[float] = mapped_column(Float)
    benchmark_start_close: Mapped[float | None] = mapped_column(Float)
    horizon_sessions: Mapped[int] = mapped_column(Integer)
    horizon_end_date: Mapped[str] = mapped_column(String(10), index=True)
    rules_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), index=True)  # open | evaluated
    outcome: Mapped[dict | None] = mapped_column(JSON)


class OptionChain(Base):
    """Index of saved option-chain snapshots (the snapshot itself is a content-hashed file)."""

    __tablename__ = "option_chains"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    spot: Mapped[float] = mapped_column(Float)
    spot_session: Mapped[str] = mapped_column(String(10))
    data_type: Mapped[str] = mapped_column(String(16))
    expiries: Mapped[int] = mapped_column(Integer)


class OptionsSignal(Base):
    """Every trading-desk decision, including NO TRADE, kept for outcome tracking (module 2, section 14)."""

    __tablename__ = "options_signals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    expiry: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(32), index=True)
    strategy: Mapped[str | None] = mapped_column(String(32))
    data_type: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))  # dry_run | paper
    chain_id: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)


class Database:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
