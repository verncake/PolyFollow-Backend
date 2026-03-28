"""
Database models for positions and trades.
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Index, Numeric, Boolean, UniqueConstraint, JSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class Position(Base):
    """User position in a market."""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_address = Column(String(42), nullable=False, index=True)
    condition_id = Column(String(66), nullable=False, index=True)
    asset_id = Column(String(128), nullable=False)

    # Market info
    market_slug = Column(String(255))
    market_title = Column(Text)
    market_icon = Column(String(512))
    outcome = Column(String(64))  # Yes/No
    outcome_index = Column(Integer)
    event_id = Column(String(64))
    event_slug = Column(String(255))
    opposite_outcome = Column(String(64))
    opposite_asset = Column(String(128))
    end_date = Column(DateTime, nullable=True)

    # Position details
    side = Column(String(4))  # BUY/SELL
    size = Column(Numeric(20, 8), default=Decimal("0"))
    avg_price = Column(Numeric(10, 6), default=Decimal("0"))  # Average entry price
    cost = Column(Numeric(20, 8), default=Decimal("0"))  # Total cost (size * price)
    total_bought = Column(Numeric(20, 8), default=Decimal("0"))

    # Value tracking
    initial_value = Column(Numeric(20, 8), default=Decimal("0"))
    current_value = Column(Numeric(20, 8), default=Decimal("0"))
    cur_price = Column(Numeric(10, 6), default=Decimal("0"))

    # Status
    status = Column(String(32), default="active")  # active, closed, pending_redeem

    # P/L
    realized_pnl = Column(Numeric(20, 8), nullable=True)
    unrealized_pnl = Column(Numeric(20, 8), nullable=True)
    percent_realized_pnl = Column(Numeric(10, 4), nullable=True)  # e.g., -100, 50
    percent_pnl = Column(Numeric(10, 4), nullable=True)

    # Redeem status
    redeemable = Column(Boolean, default=False)
    mergeable = Column(Boolean, default=False)
    negative_risk = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Sync metadata
    last_trade_timestamp = Column(Integer, nullable=True)
    trade_count = Column(Integer, default=0)

    # Source tracking
    source = Column(String(32), default="positions")  # positions, closed-positions

    # Raw data - store complete original API response
    raw_data = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_positions_user_status", "user_address", "status"),
        Index("idx_positions_user_updated", "user_address", "updated_at"),
        # Active/pending positions: unique per user + condition + asset_id + status
        # asset_id is required to distinguish multiple positions on the same market
        UniqueConstraint("user_address", "condition_id", "asset_id", "status", name="uq_positions_user_condition_status"),
        # Closed positions: unique per user + condition + asset_id + closed_at to handle re-trading
        # Each close of the same position has a different closed_at timestamp
        UniqueConstraint("user_address", "condition_id", "asset_id", "closed_at", name="uq_positions_user_condition_closed"),
    )


class Trade(Base):
    """Individual trade record."""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_address = Column(String(42), nullable=False, index=True)
    condition_id = Column(String(66), nullable=False, index=True)
    asset_id = Column(String(128), nullable=False)

    # Trade details
    side = Column(String(4))  # BUY/SELL
    size = Column(Numeric(20, 8), default=Decimal("0"))
    price = Column(Numeric(10, 6), default=Decimal("0"))
    fee = Column(Numeric(20, 8), nullable=True)

    # Market info
    market_title = Column(Text)
    market_slug = Column(String(255))
    outcome = Column(String(64))
    transaction_hash = Column(String(128))

    # Timestamps
    timestamp = Column(Integer, nullable=False)  # Unix timestamp
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_trades_user_timestamp", "user_address", "timestamp"),
        Index("idx_trades_condition", "condition_id"),
    )


class Activity(Base):
    """User activity record (trades, redemptions, etc.)."""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_address = Column(String(42), nullable=False, index=True)
    condition_id = Column(String(66), nullable=False, index=True)
    asset_id = Column(String(128), nullable=False)

    # Activity type: TRADE, REDEEM, SPLIT, MERGE, REWARD
    activity_type = Column(String(32), nullable=False, index=True)

    # Trade details (null for non-trade activities)
    side = Column(String(4))  # BUY, SELL
    size = Column(Numeric(20, 8), default=Decimal("0"))
    price = Column(Numeric(10, 6), default=Decimal("0"))
    fee = Column(Numeric(20, 8), nullable=True)

    # Market info
    market_title = Column(Text)
    market_slug = Column(String(255))
    outcome = Column(String(64))
    icon = Column(String(512))

    # Transaction
    transaction_hash = Column(String(128))

    # Timestamps
    timestamp = Column(Integer, nullable=False)  # Unix timestamp from API
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_activities_user_timestamp", "user_address", "timestamp"),
        Index("idx_activities_condition_type", "condition_id", "activity_type"),
        UniqueConstraint("user_address", "condition_id", "asset_id", "activity_type", "timestamp", name="uq_activity_identity"),
    )


class SyncState(Base):
    """Tracks sync state for incremental updates."""
    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_address = Column(String(42), nullable=False, unique=True, index=True)

    # Last sync timestamps (oldest trade timestamp we've synced)
    positions_synced_at = Column(DateTime, nullable=True)
    trades_synced_at = Column(DateTime, nullable=True)

    # Status
    positions_sync_status = Column(String(16), default="pending")  # pending, completed, failed
    trades_sync_status = Column(String(16), default="pending")

    # Error info
    last_error = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
