"""
Database service for positions and trades storage.
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func, and_, case, update, or_
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.models.position import Base, Position, Trade, SyncState, Activity


class DatabaseService:
    """Service for managing positions and trades in PostgreSQL via Supabase."""

    def __init__(self):
        settings = get_settings()
        self.database_url = settings.database_url
        self.pool = None
        self.session_factory = None

    async def initialize(self):
        """Initialize the database connection pool."""
        if not self.database_url:
            raise ValueError("DATABASE_URL not configured")

        # Convert postgresql:// to postgresql+asyncpg:// for async support
        # SQLAlchemy's create_async_engine needs the +asyncpg suffix
        db_url = self.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Remove pgbouncer query param if present - asyncpg doesn't accept it
        db_url = db_url.split("?")[0]

        # Create async engine with pgbouncer-compatible settings
        # statement_cache_size=0 required for pgbouncer transaction mode
        self.engine = create_async_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True,
            connect_args={
                "statement_cache_size": 0,
            },
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create tables if they don't exist
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self):
        """Get a database session."""
        if not self.session_factory:
            await self.initialize()

        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def upsert_trades(self, user_address: str, trades: list[dict]) -> int:
        """Insert or update trades. Returns count of new trades."""
        if not trades:
            return 0

        async with self.get_session() as session:
            new_count = 0
            for t in trades:
                stmt = insert(Trade).values(
                    user_address=user_address.lower(),
                    condition_id=t.get("conditionId", ""),
                    asset_id=t.get("asset", ""),
                    side=t.get("side", ""),
                    size=Decimal(str(t.get("size", 0))),
                    price=Decimal(str(t.get("price", 0))),
                    fee=Decimal(str(t.get("fee", 0))) if t.get("fee") else None,
                    market_title=t.get("title", ""),
                    market_slug=t.get("slug", ""),
                    outcome=t.get("outcome", ""),
                    transaction_hash=t.get("transactionHash", ""),
                    timestamp=t.get("timestamp", 0),
                )
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["user_address", "condition_id", "side", "size", "price", "timestamp"]
                )
                result = await session.execute(stmt)
                new_count += result.rowcount

            return new_count

    async def get_user_trades_count(
        self,
        user_address: str,
        since_timestamp: Optional[int] = None,
        market_slug: Optional[str] = None,
    ) -> int:
        """Get total count of trades for a user, optionally filtered."""
        async with self.get_session() as session:
            query = select(func.count(Trade.id)).where(Trade.user_address == user_address.lower())
            if since_timestamp:
                query = query.where(Trade.timestamp >= since_timestamp)
            if market_slug:
                query = query.where(Trade.market_slug == market_slug)
            result = await session.execute(query)
            return result.scalar() or 0

    async def get_latest_trade_timestamp(self, user_address: str) -> Optional[int]:
        """Get the timestamp of the most recent trade for a user."""
        async with self.get_session() as session:
            stmt = select(func.max(Trade.timestamp)).where(
                Trade.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            return result.scalar()

    async def delete_trades_for_address(self, user_address: str) -> int:
        """Delete all trades for a user address. Returns count of deleted trades."""
        async with self.get_session() as session:
            stmt = Trade.__table__.delete().where(
                Trade.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            return result.rowcount

    async def get_user_trades(
        self,
        user_address: str,
        since_timestamp: Optional[int] = None,
        limit: int = 1000,
        offset: int = 0,
        market_slug: Optional[str] = None,
    ) -> list[dict]:
        """Get trades for a user, optionally filtered by timestamp, market, with pagination."""
        async with self.get_session() as session:
            query = select(Trade).where(Trade.user_address == user_address.lower())
            if since_timestamp:
                query = query.where(Trade.timestamp >= since_timestamp)
            if market_slug:
                query = query.where(Trade.market_slug == market_slug)
            query = query.order_by(Trade.timestamp.desc()).limit(limit).offset(offset)

            result = await session.execute(query)
            trades = result.scalars().all()

            return [
                {
                    "condition_id": t.condition_id,
                    "asset_id": t.asset_id,
                    "side": t.side,
                    "size": float(t.size),
                    "price": float(t.price),
                    "fee": float(t.fee) if t.fee else 0,
                    "market_title": t.market_title,
                    "market_slug": t.market_slug,
                    "outcome": t.outcome,
                    "transaction_hash": t.transaction_hash,
                    "timestamp": t.timestamp,
                }
                for t in trades
            ]

    async def upsert_positions(self, user_address: str, positions: list[dict]) -> int:
        """Insert or update positions. Returns count of upserted positions.

        For closed positions, uses (user_address, condition_id, closed_at) as unique key
        to handle cases where the same position is closed and reopened multiple times.

        For active positions, uses (user_address, condition_id, status) as unique key.
        Note: The Polymarket API doesn't return 'side' for positions.
        """
        if not positions:
            return 0

        async with self.get_session() as session:
            upsert_count = 0
            for p in positions:
                status = p.get("status", "active")
                is_closed = status == "closed"

                # For closed positions, closed_at is required for uniqueness
                # The API returns 'timestamp' for closed positions as the close time
                closed_at = None
                if is_closed:
                    ts = p.get("timestamp")
                    if ts:
                        closed_at = datetime.fromtimestamp(ts)

                values = {
                    "user_address": user_address.lower(),
                    "condition_id": p.get("conditionId", ""),
                    "asset_id": p.get("asset", ""),
                    "side": p.get("side") or "",
                    "size": Decimal(str(p.get("size", 0))),
                    "avg_price": Decimal(str(p.get("avgPrice", 0))),
                    "cost": Decimal(str(p.get("cost", 0))) if p.get("cost") else Decimal(str(p.get("size", 0))) * Decimal(str(p.get("avgPrice", 0))),
                    "market_title": p.get("title", ""),
                    "market_slug": p.get("slug", ""),
                    "outcome": p.get("outcome", ""),
                    "status": status,
                    "unrealized_pnl": Decimal(str(p.get("cashPnl", 0))) if p.get("cashPnl") is not None else None,
                    "realized_pnl": Decimal(str(p.get("realizedPnl", 0))) if p.get("realizedPnl") is not None else None,
                    "last_trade_timestamp": p.get("lastTradeTimestamp"),
                    "trade_count": p.get("tradeCount", 0),
                    "closed_at": closed_at,
                }

                if is_closed:
                    # For closed positions, use (user_address, condition_id, asset_id, closed_at) in unique constraint
                    # to match the actual unique constraint on the model
                    stmt = insert(Position).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_address", "condition_id", "asset_id", "closed_at"],
                        set_={
                            "size": values["size"],
                            "avg_price": values["avg_price"],
                            "cost": values["cost"],
                            "realized_pnl": values["realized_pnl"],
                            "status": values["status"],
                            "updated_at": datetime.utcnow(),
                        }
                    )
                else:
                    # For active positions, use (user_address, condition_id, asset_id, status) as unique constraint
                    stmt = insert(Position).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_address", "condition_id", "asset_id", "status"],
                        set_={
                            "size": values["size"],
                            "avg_price": values["avg_price"],
                            "cost": values["cost"],
                            "unrealized_pnl": values["unrealized_pnl"],
                            "last_trade_timestamp": values["last_trade_timestamp"],
                            "trade_count": values["trade_count"],
                            "updated_at": datetime.utcnow(),
                        }
                    )
                result = await session.execute(stmt)
                upsert_count += 1  # Count all attempts as upserted

            return upsert_count

    async def get_user_positions(
        self,
        user_address: str,
        status: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Get positions for a user, optionally filtered by status."""
        async with self.get_session() as session:
            query = select(Position).where(Position.user_address == user_address.lower())
            if status and status != "all":
                if status == "active":
                    # Include both active and pending_redeem for active query
                    query = query.where(Position.status.in_(["active", "pending_redeem"]))
                else:
                    query = query.where(Position.status == status)
            query = query.order_by(Position.updated_at.desc()).limit(limit)

            result = await session.execute(query)
            positions = result.scalars().all()

            return [
                {
                    "condition_id": p.condition_id,
                    "asset_id": p.asset_id,
                    "side": p.side,
                    "size": float(p.size),
                    "avg_price": float(p.avg_price),
                    "cost": float(p.cost),
                    "market_title": p.market_title,
                    "market_slug": p.market_slug,
                    "market_icon": p.market_icon,
                    "outcome": p.outcome,
                    "outcome_index": p.outcome_index,
                    "event_id": p.event_id,
                    "event_slug": p.event_slug,
                    "opposite_outcome": p.opposite_outcome,
                    "opposite_asset": p.opposite_asset,
                    "end_date": p.end_date.isoformat() if p.end_date else None,
                    "total_bought": float(p.total_bought) if p.total_bought else 0,
                    "initial_value": float(p.initial_value) if p.initial_value else 0,
                    "current_value": float(p.current_value) if p.current_value else 0,
                    "cur_price": float(p.cur_price) if p.cur_price else 0,
                    "status": p.status,
                    "realized_pnl": float(p.realized_pnl) if p.realized_pnl else 0,
                    "unrealized_pnl": float(p.unrealized_pnl) if p.unrealized_pnl else 0,
                    "percent_realized_pnl": float(p.percent_realized_pnl) if p.percent_realized_pnl else None,
                    "percent_pnl": float(p.percent_pnl) if p.percent_pnl else None,
                    "redeemable": p.redeemable,
                    "mergeable": p.mergeable,
                    "negative_risk": p.negative_risk,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                    "closed_at_timestamp": int(p.closed_at.timestamp()) if p.closed_at else None,
                    "trade_count": p.trade_count,
                    "source": p.source,
                    "raw_data": p.raw_data,
                }
                for p in positions
            ]

    async def get_user_closed_positions(
        self,
        user_address: str,
        since_timestamp: Optional[int] = None,
        limit: int = 10000,
    ) -> list[dict]:
        """Get closed positions for a user, optionally filtered by closed_at timestamp."""
        async with self.get_session() as session:
            query = select(Position).where(
                and_(
                    Position.user_address == user_address.lower(),
                    Position.status == "closed",
                    Position.closed_at.isnot(None),
                )
            )
            if since_timestamp:
                # Convert since_timestamp (Unix int) to datetime for comparison
                since_dt = datetime.fromtimestamp(since_timestamp)
                query = query.where(Position.closed_at >= since_dt)
            query = query.order_by(Position.closed_at.asc()).limit(limit)

            result = await session.execute(query)
            positions = result.scalars().all()

            return [
                {
                    "condition_id": p.condition_id,
                    "asset_id": p.asset_id,
                    "side": p.side,
                    "size": float(p.size),
                    "avg_price": float(p.avg_price),
                    "cost": float(p.cost),
                    "market_title": p.market_title,
                    "market_slug": p.market_slug,
                    "outcome": p.outcome,
                    "status": p.status,
                    "realized_pnl": float(p.realized_pnl) if p.realized_pnl else 0,
                    "unrealized_pnl": float(p.unrealized_pnl) if p.unrealized_pnl else 0,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                    "closed_at_timestamp": int(p.closed_at.timestamp()) if p.closed_at else None,
                    "trade_count": p.trade_count,
                }
                for p in positions
            ]

    async def delete_active_positions_for_closed(
        self,
        user_address: str,
        closed_positions: list[dict],
    ) -> int:
        """Delete active positions that have corresponding closed positions.

        When a position transitions from active to closed, we need to delete
        the active position row before inserting the closed position to avoid
        unique constraint conflicts.

        Returns the count of deleted positions.
        """
        if not closed_positions:
            return 0

        async with self.get_session() as session:
            deleted_count = 0
            for p in closed_positions:
                condition_id = p.get("conditionId", "")
                if not condition_id:
                    continue

                # Delete any active position for this condition_id
                stmt = Position.__table__.delete().where(
                    and_(
                        Position.user_address == user_address.lower(),
                        Position.condition_id == condition_id,
                        Position.status == "active",
                    )
                )
                result = await session.execute(stmt)
                deleted_count += result.rowcount

            return deleted_count

    async def delete_all_positions_for_address(self, user_address: str) -> int:
        """Delete all positions for a user address. Returns count of deleted positions."""
        async with self.get_session() as session:
            stmt = Position.__table__.delete().where(
                Position.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            return result.rowcount

    async def upsert_positions_enhanced(
        self,
        user_address: str,
        positions: list[dict],
    ) -> int:
        """
        Insert or update positions with enhanced P/L data.

        This handles both active and closed positions with properly calculated
        realized and unrealized P/L values.

        Args:
            user_address: User wallet address
            positions: List of position dicts with calculated P/L

        Returns:
            Count of upserted positions
        """
        if not positions:
            return 0

        async with self.get_session() as session:
            upsert_count = 0

            for p in positions:
                status = p.get("status", "active")
                closed_at = p.get("closed_at")

                # Parse end_date if present
                end_date = p.get("end_date")
                if end_date and isinstance(end_date, str):
                    try:
                        end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        # Strip timezone to store as naive timestamp
                        if end_date.tzinfo is not None:
                            end_date = end_date.replace(tzinfo=None)
                    except Exception:
                        end_date = None

                values = {
                    "user_address": user_address.lower(),
                    "condition_id": p.get("condition_id", ""),
                    "asset_id": p.get("asset_id", ""),
                    "side": p.get("side", ""),
                    "size": Decimal(str(p.get("size", 0))),
                    "avg_price": Decimal(str(p.get("avg_price", 0))),
                    "cost": Decimal(str(p.get("cost", 0))),
                    "market_title": p.get("market_title", ""),
                    "market_slug": p.get("market_slug", ""),
                    "market_icon": p.get("market_icon"),
                    "outcome": p.get("outcome", ""),
                    "outcome_index": p.get("outcome_index"),
                    "event_id": p.get("event_id"),
                    "event_slug": p.get("event_slug"),
                    "opposite_outcome": p.get("opposite_outcome"),
                    "opposite_asset": p.get("opposite_asset"),
                    "end_date": end_date,
                    "total_bought": Decimal(str(p.get("total_bought", 0))),
                    "initial_value": Decimal(str(p.get("initial_value", 0))),
                    "current_value": Decimal(str(p.get("current_value", 0))),
                    "cur_price": Decimal(str(p.get("cur_price", 0))),
                    "status": status,
                    "realized_pnl": Decimal(str(p.get("realized_pnl", 0))),
                    "unrealized_pnl": Decimal(str(p.get("unrealized_pnl", 0))),
                    "percent_realized_pnl": Decimal(str(p.get("percent_realized_pnl", 0))) if p.get("percent_realized_pnl") is not None else None,
                    "percent_pnl": Decimal(str(p.get("percent_pnl", 0))) if p.get("percent_pnl") is not None else None,
                    "redeemable": p.get("redeemable", False),
                    "mergeable": p.get("mergeable", False),
                    "negative_risk": p.get("negative_risk", False),
                    "trade_count": p.get("trade_count", 0),
                    "closed_at": closed_at,
                    "source": p.get("source", "positions"),
                    "raw_data": p.get("raw_data"),
                }

                if status == "closed" and closed_at:
                    # For closed positions, use (user_address, condition_id, asset_id, closed_at) in unique constraint
                    stmt = insert(Position).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_address", "condition_id", "asset_id", "closed_at"],
                        set_={
                            "size": values["size"],
                            "avg_price": values["avg_price"],
                            "cost": values["cost"],
                            "realized_pnl": values["realized_pnl"],
                            "status": values["status"],
                            "unrealized_pnl": values["unrealized_pnl"],
                            "percent_realized_pnl": values["percent_realized_pnl"],
                            "percent_pnl": values["percent_pnl"],
                            "current_value": values["current_value"],
                            "redeemable": values["redeemable"],
                            "updated_at": datetime.utcnow(),
                            "raw_data": values["raw_data"],
                        }
                    )
                else:
                    # For active/pending_redeem positions, use (user_address, condition_id, asset_id, status)
                    stmt = insert(Position).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_address", "condition_id", "asset_id", "status"],
                        set_={
                            "size": values["size"],
                            "avg_price": values["avg_price"],
                            "cost": values["cost"],
                            "realized_pnl": values["realized_pnl"],
                            "unrealized_pnl": values["unrealized_pnl"],
                            "percent_realized_pnl": values["percent_realized_pnl"],
                            "percent_pnl": values["percent_pnl"],
                            "current_value": values["current_value"],
                            "redeemable": values["redeemable"],
                            "status": values["status"],
                            "trade_count": values["trade_count"],
                            "updated_at": datetime.utcnow(),
                            "raw_data": values["raw_data"],
                        }
                    )

                await session.execute(stmt)
                upsert_count += 1

            return upsert_count

    async def calculate_realized_pnl(self, user_address: str) -> dict[str, dict]:
        """
        Calculate realized PnL for each market from stored trades.

        Returns a dict mapping condition_id to:
            - realized_pnl: net PnL
            - cost: total cost of buys
            - proceeds: total proceeds from sells
            - trade_count: number of trades
        """
        async with self.get_session() as session:
            # Get all trades grouped by condition
            stmt = select(
                Trade.condition_id,
                Trade.market_title,
                func.sum(
                    case(
                        (Trade.side == "BUY", Trade.size * Trade.price),
                        else_=0
                    )
                ).label("cost"),
                func.sum(
                    case(
                        (Trade.side == "SELL", Trade.size * Trade.price),
                        else_=0
                    )
                ).label("proceeds"),
                func.count(Trade.id).label("trade_count"),
            ).where(
                and_(
                    Trade.user_address == user_address.lower(),
                    Trade.side.in_(["BUY", "SELL"])
                )
            ).group_by(
                Trade.condition_id, Trade.market_title
            )

            result = await session.execute(stmt)
            rows = result.all()

            pnl_by_market = {}
            for row in rows:
                cost = Decimal(str(row.cost or 0))
                proceeds = Decimal(str(row.proceeds or 0))
                realized_pnl = proceeds - cost

                pnl_by_market[row.condition_id] = {
                    "realized_pnl": realized_pnl,
                    "cost": cost,
                    "proceeds": proceeds,
                    "trade_count": row.trade_count,
                    "market_title": row.market_title,
                }

            return pnl_by_market

    async def get_sync_state(self, user_address: str) -> Optional[SyncState]:
        """Get the sync state for a user."""
        async with self.get_session() as session:
            stmt = select(SyncState).where(
                SyncState.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_stale_sync_addresses(self, stale_minutes: int = 5) -> list[str]:
        """Get addresses with stale sync data (older than stale_minutes).

        Returns list of user addresses that need syncing.
        """
        async with self.get_session() as session:
            cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
            # Find addresses where trades_synced_at is None or older than cutoff
            # Also include addresses that have never been synced
            stmt = select(SyncState.user_address).where(
                or_(
                    SyncState.trades_synced_at.is_(None),
                    SyncState.trades_synced_at < cutoff,
                )
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_all_sync_addresses(self) -> list[str]:
        """Get all addresses that have a sync state entry."""
        async with self.get_session() as session:
            stmt = select(SyncState.user_address)
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def upsert_sync_state(
        self,
        user_address: str,
        positions_synced_at: Optional[datetime] = None,
        trades_synced_at: Optional[datetime] = None,
        positions_status: Optional[str] = None,
        trades_status: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Update or create sync state for a user."""
        async with self.get_session() as session:
            stmt = select(SyncState).where(
                SyncState.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            sync_state = result.scalar_one_or_none()

            if sync_state:
                if positions_synced_at is not None:
                    sync_state.positions_synced_at = positions_synced_at
                if trades_synced_at is not None:
                    sync_state.trades_synced_at = trades_synced_at
                if positions_status:
                    sync_state.positions_sync_status = positions_status
                if trades_status:
                    sync_state.trades_sync_status = trades_status
                if error is not None:
                    sync_state.last_error = error
                sync_state.updated_at = datetime.utcnow()
            else:
                sync_state = SyncState(
                    user_address=user_address.lower(),
                    positions_synced_at=positions_synced_at,
                    trades_synced_at=trades_synced_at,
                    positions_sync_status=positions_status or "completed",
                    trades_sync_status=trades_status or "completed",
                    last_error=error,
                )
                session.add(sync_state)

    async def upsert_activities(self, user_address: str, activities: list[dict]) -> int:
        """Insert or update activities. Returns count of upserted activities.

        Activities include trades, redemptions, splits, merges, etc.
        Linked to positions via condition_id and asset_id.

        Uses INSERT ... ON CONFLICT DO NOTHING for atomic, race-condition-safe upserts.

        Args:
            user_address: User wallet address
            activities: List of activity dicts from Polymarket API

        Returns:
            Count of upserted activities
        """
        if not activities:
            return 0

        async with self.get_session() as session:
            upsert_count = 0
            for a in activities:
                # Use INSERT ... ON CONFLICT DO NOTHING for atomic upsert
                # This avoids the race condition of SELECT-then-INSERT
                stmt = insert(Activity).values(
                    user_address=user_address.lower(),
                    condition_id=a.get("conditionId", ""),
                    asset_id=a.get("asset", ""),
                    activity_type=a.get("type", "TRADE"),
                    side=a.get("side") or "",
                    size=Decimal(str(a.get("size", 0))),
                    price=Decimal(str(a.get("price", 0))),
                    fee=Decimal(str(a.get("fee", 0))) if a.get("fee") else None,
                    market_title=a.get("title", ""),
                    market_slug=a.get("slug", ""),
                    icon=a.get("icon", ""),
                    outcome=a.get("outcome", ""),
                    transaction_hash=a.get("transactionHash", ""),
                    timestamp=a.get("timestamp", 0),
                )
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["user_address", "condition_id", "asset_id", "activity_type", "timestamp"]
                )
                result = await session.execute(stmt)
                upsert_count += result.rowcount

            await session.commit()
            return upsert_count

    async def get_user_activities(
        self,
        user_address: str,
        activity_type: Optional[str] = None,
        condition_id: Optional[str] = None,
        since_timestamp: Optional[int] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict]:
        """Get activities for a user, optionally filtered.

        Args:
            user_address: User wallet address
            activity_type: Filter by activity type (TRADE, REDEEM, etc.)
            condition_id: Filter by condition ID
            since_timestamp: Filter by timestamp (Unix int)
            limit: Max number of results
            offset: Pagination offset

        Returns:
            List of activity dicts
        """
        async with self.get_session() as session:
            query = select(Activity).where(Activity.user_address == user_address.lower())
            if activity_type:
                query = query.where(Activity.activity_type == activity_type)
            if condition_id:
                query = query.where(Activity.condition_id == condition_id)
            if since_timestamp:
                query = query.where(Activity.timestamp >= since_timestamp)
            query = query.order_by(Activity.timestamp.desc()).limit(limit).offset(offset)

            result = await session.execute(query)
            activities = result.scalars().all()

            return [
                {
                    "type": a.activity_type,
                    "title": a.market_title,
                    "slug": a.market_slug,
                    "icon": a.icon,
                    "outcome": a.outcome,
                    "side": a.side,
                    "usdcSize": float(a.size) * float(a.price) if a.size and a.price else 0,
                    "size": float(a.size) if a.size else 0,
                    "price": float(a.price) if a.price else 0,
                    "timestamp": a.timestamp,
                    "market": a.condition_id,
                    "condition_id": a.condition_id,
                    "asset_id": a.asset_id,
                    "fee": float(a.fee) if a.fee else 0,
                    "transaction_hash": a.transaction_hash,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in activities
            ]

    async def get_latest_activity_timestamp(self, user_address: str) -> Optional[int]:
        """Get the timestamp of the most recent activity for a user."""
        async with self.get_session() as session:
            stmt = select(func.max(Activity.timestamp)).where(
                Activity.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            return result.scalar()

    async def get_activity_for_condition(
        self,
        user_address: str,
        condition_id: str,
        asset_id: str,
        activity_type: str,
    ) -> Optional[dict]:
        """Get the most recent activity of a specific type for a condition/asset pair.

        Used to find proxy timestamps for pending_redeem positions.
        For REDEEM activities (which have empty asset_id), we match by condition_id only.

        Args:
            user_address: User wallet address
            condition_id: Market condition ID
            asset_id: Asset ID (can be empty string for REDEEM)
            activity_type: Activity type (e.g., REDEEM)

        Returns:
            Activity dict or None
        """
        async with self.get_session() as session:
            # Build query conditions
            conditions = [
                Activity.user_address == user_address.lower(),
                Activity.condition_id == condition_id,
                Activity.activity_type == activity_type,
            ]
            # For non-REDEEM activities, also filter by asset_id
            if asset_id and activity_type != "REDEEM":
                conditions.append(Activity.asset_id == asset_id)

            query = select(Activity).where(
                and_(*conditions)
            ).order_by(Activity.timestamp.desc()).limit(1)

            result = await session.execute(query)
            activity = result.scalar_one_or_none()

            if not activity:
                return None

            return {
                "condition_id": activity.condition_id,
                "asset_id": activity.asset_id,
                "activity_type": activity.activity_type,
                "side": activity.side,
                "size": float(activity.size),
                "price": float(activity.price),
                "fee": float(activity.fee) if activity.fee else 0,
                "market_title": activity.market_title,
                "market_slug": activity.market_slug,
                "outcome": activity.outcome,
                "transaction_hash": activity.transaction_hash,
                "timestamp": activity.timestamp,
                "created_at": activity.created_at.isoformat() if activity.created_at else None,
            }

    async def delete_activities_for_address(self, user_address: str) -> int:
        """Delete all activities for a user address. Returns count of deleted activities."""
        async with self.get_session() as session:
            stmt = Activity.__table__.delete().where(
                Activity.user_address == user_address.lower()
            )
            result = await session.execute(stmt)
            return result.rowcount

    async def get_activities_for_conditions(
        self,
        user_address: str,
        condition_ids: list[tuple[str, str]],
        activity_type: str = "TRADE",
    ) -> dict[tuple[str, str], Optional[dict]]:
        """Batch fetch activities for multiple condition_id/asset_id pairs.

        Used to find proxy timestamps for pending_redeem positions efficiently
        (avoids N+1 queries when enriching positions).

        Args:
            user_address: User wallet address
            condition_ids: List of (condition_id, asset_id) tuples
            activity_type: Activity type (default: TRADE)

        Returns:
            Dict mapping (condition_id, asset_id) -> latest activity dict or None
        """
        if not condition_ids:
            return {}

        async with self.get_session() as session:
            # Build query to get latest activity per (condition_id, asset_id) pair
            # Using a subquery approach for PostgreSQL
            subq = (
                select(
                    Activity.condition_id,
                    Activity.asset_id,
                    func.max(Activity.timestamp).label("max_timestamp"),
                )
                .where(
                    and_(
                        Activity.user_address == user_address.lower(),
                        Activity.condition_id.in_([c[0] for c in condition_ids]),
                        Activity.activity_type == activity_type,
                    )
                )
                .group_by(Activity.condition_id, Activity.asset_id)
            ).subquery()

            # Main query to get full activity records
            query = (
                select(Activity)
                .join(
                    subq,
                    and_(
                        Activity.condition_id == subq.c.condition_id,
                        Activity.asset_id == subq.c.asset_id,
                        Activity.timestamp == subq.c.max_timestamp,
                    )
                )
            )

            result = await session.execute(query)
            activities = result.scalars().all()

            # Build result dict
            result_dict = {}
            for activity in activities:
                key = (activity.condition_id, activity.asset_id)
                result_dict[key] = {
                    "condition_id": activity.condition_id,
                    "asset_id": activity.asset_id,
                    "activity_type": activity.activity_type,
                    "side": activity.side,
                    "size": float(activity.size),
                    "price": float(activity.price),
                    "fee": float(activity.fee) if activity.fee else 0,
                    "market_title": activity.market_title,
                    "market_slug": activity.market_slug,
                    "outcome": activity.outcome,
                    "transaction_hash": activity.transaction_hash,
                    "timestamp": activity.timestamp,
                    "created_at": activity.created_at.isoformat() if activity.created_at else None,
                }

            return result_dict


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_db_service() -> DatabaseService:
    """Get the database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
