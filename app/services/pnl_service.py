"""
PnL Calculation Service.

Calculates accurate Profit/Loss from stored trades with incremental sync support.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
import asyncio
import logging

from app.services.data import get_data_client
from app.core.database import get_db_service
from app.core.redis import (
    store_pnl_history,
    get_pnl_history as get_pnl_history_from_redis,
    get_pnl_history_ttl_seconds,
)

logger = logging.getLogger(__name__)

# Rate limiting: delay between API calls to avoid rate limiting
API_CALL_DELAY = 0.5  # seconds between calls


class PnLService:
    """Service for calculating accurate PnL from trades."""

    def __init__(self):
        self.data_client = get_data_client()
        self.db = get_db_service()

    async def sync_trades_for_address(
        self,
        user_address: str,
        lookback_days: int = 365,
        force_refresh: bool = False,
    ) -> dict:
        """
        Sync trades for a user address using incremental updates.

        Args:
            user_address: Wallet address to sync
            lookback_days: Only sync trades within this many days (for initial sync)
            force_refresh: If True, delete existing trades and re-fetch all

        Returns:
            dict with sync stats (new_trades, last_timestamp, etc.)
        """
        # For force refresh, delete existing trades first
        if force_refresh:
            await self.db.delete_trades_for_address(user_address)
            latest_timestamp = None
        else:
            # Get the latest synced timestamp from our DB
            latest_timestamp = await self.db.get_latest_trade_timestamp(user_address)

        # Fetch ALL trades using pagination
        all_trades = []
        limit = 5000
        offset = 0
        max_pages = 100  # Safety limit

        for page in range(max_pages):
            trades = await self.data_client.get_trades(
                user=user_address,
                limit=limit,
                offset=offset,
            )

            if not trades:
                break

            all_trades.extend(trades)
            logger.info(
                f"Syncing {user_address}: fetched {len(trades)} trades "
                f"(offset {offset}, total {len(all_trades)})"
            )

            if len(trades) < limit:
                break  # Last page

            offset += limit
            await asyncio.sleep(API_CALL_DELAY)

        if not all_trades:
            return {"new_trades": 0, "status": "no_trades"}

        # For incremental sync (not force_refresh), filter by latest_timestamp
        # to avoid re-inserting trades we already have
        if latest_timestamp:
            all_trades = [t for t in all_trades if t.get("timestamp", 0) >= latest_timestamp]
            logger.info(f"After incremental filter: {len(all_trades)} trades since {latest_timestamp}")

        # Also apply lookback_days filter only for initial sync (when latest_timestamp is None)
        if latest_timestamp is None and lookback_days:
            cutoff = int((datetime.utcnow() - timedelta(days=lookback_days)).timestamp())
            before = len(all_trades)
            all_trades = [t for t in all_trades if t.get("timestamp", 0) >= cutoff]
            logger.info(f"After lookback filter: {len(all_trades)} trades (removed {before - len(all_trades)} older than {lookback_days} days)")

        # Insert into database
        new_count = await self.db.upsert_trades(user_address, all_trades)

        # Update sync state
        max_ts = max((t.get("timestamp", 0) for t in all_trades), default=0)
        await self.db.upsert_sync_state(
            user_address,
            trades_synced_at=datetime.utcnow(),
            trades_status="completed",
        )

        return {
            "new_trades": new_count,
            "total_trades_synced": len(all_trades),
            "last_trade_timestamp": max_ts,
            "status": "completed",
        }

    async def sync_activity_for_address(
        self,
        user_address: str,
        force_refresh: bool = False,
    ) -> dict:
        """
        Sync user activity (trades, redemptions, etc.) from /activity API.

        Fetches all activity with pagination and stores:
        1. In activities table (full activity data including REDEEM types)
        2. In trades table (for backward compatibility with trade history)

        Activity data provides detailed history including:
        - transaction hash, timestamp, side, size, price
        - Links to positions via condition_id and asset_id

        Args:
            user_address: Wallet address to sync
            force_refresh: If True, delete existing activities and re-fetch all

        Returns:
            dict with sync stats (new_activities, last_timestamp, etc.)
        """
        if force_refresh:
            await self.db.delete_activities_for_address(user_address)
            await self.db.delete_trades_for_address(user_address)
            latest_timestamp = None
        else:
            latest_timestamp = await self.db.get_latest_activity_timestamp(user_address)

        # Fetch ALL activity using pagination
        all_activities = []
        limit = 50  # API max is 50
        offset = 0
        max_pages = 1000  # Safety limit

        for page in range(max_pages):
            activities = await self.data_client.get_activity(
                user=user_address,
                limit=limit,
                offset=offset,
                sort_by="TIMESTAMP",
                sort_direction="DESC",
            )

            if not activities:
                logger.info(
                    f"Syncing activity for {user_address}: empty result at offset {offset}, "
                    f"total fetched: {len(all_activities)}"
                )
                break

            all_activities.extend(activities)
            logger.info(
                f"Syncing activity for {user_address}: fetched {len(activities)} activities "
                f"(offset {offset}, total {len(all_activities)})"
            )

            if len(activities) < limit:
                break  # Last page

            offset += limit
            await asyncio.sleep(API_CALL_DELAY)

        if not all_activities:
            return {"new_activities": 0, "status": "no_activities"}

        # Filter by latest_timestamp for incremental sync
        if latest_timestamp:
            all_activities = [a for a in all_activities if a.get("timestamp", 0) >= latest_timestamp]
            logger.info(f"After incremental filter: {len(all_activities)} activities since {latest_timestamp}")

        # Store full activity data in activities table (includes REDEEM, SPLIT, MERGE types)
        activities_count = await self.db.upsert_activities(user_address, all_activities)

        # Convert activity to trade format and insert for backward compatibility
        trades = []
        for a in all_activities:
            # Only convert TRADE activities to trades
            if a.get("type") == "TRADE":
                trade = {
                    "conditionId": a.get("conditionId", ""),
                    "asset": a.get("asset", ""),
                    "side": a.get("side", ""),
                    "size": a.get("size", 0),
                    "price": a.get("price", 0),
                    "timestamp": a.get("timestamp", 0),
                    "transactionHash": a.get("transactionHash", ""),
                    "market_title": a.get("title", ""),
                    "market_slug": a.get("slug", ""),
                    "outcome": a.get("outcome", ""),
                }
                trades.append(trade)

        trades_count = 0
        if trades:
            trades_count = await self.db.upsert_trades(user_address, trades)

        # Update sync state
        max_ts = max((a.get("timestamp", 0) for a in all_activities), default=0)
        await self.db.upsert_sync_state(
            user_address,
            trades_synced_at=datetime.utcnow(),
            trades_status="completed",
        )

        return {
            "new_activities": activities_count,
            "new_trades": trades_count,
            "total_activities_synced": len(all_activities),
            "last_timestamp": max_ts,
            "status": "completed",
        }

    async def sync_positions_for_address(
        self,
        user_address: str,
        force_refresh: bool = False,
    ) -> dict:
        """
        Sync positions for a user address.

        Fetches active and closed positions from DataClient and stores them
        in the database for later use in PnL calculations.

        Uses incremental sync - closed positions are fetched with pagination to get
        all historical closes.

        Args:
            user_address: Wallet address to sync
            force_refresh: If True, ignore last_sync_check and re-fetch closed positions

        Returns:
            dict with sync stats (positions_upserted, etc.)
        """
        # Get sync state to check if we should do incremental sync
        sync_state = await self.db.get_sync_state(user_address)

        # Fetch active positions first with pagination
        # IMPORTANT: Continue until we get an EMPTY result, not just when len(batch) < limit
        active_positions = []
        positions_limit = 1000
        positions_offset = 0
        max_pages = 500  # Increased to handle users with many positions

        for page in range(max_pages):
            batch = await self.data_client.get_positions(
                user=user_address,
                limit=positions_limit,
                offset=positions_offset,
            )
            if not batch:
                logger.info(
                    f"Syncing {user_address}: empty result at offset {positions_offset}, "
                    f"total active positions fetched: {len(active_positions)}"
                )
                break
            active_positions.extend(batch)
            logger.info(
                f"Syncing {user_address}: fetched {len(batch)} active positions "
                f"(offset {positions_offset}, total {len(active_positions)})"
            )
            if len(batch) == 0:
                break  # No more data
            positions_offset += positions_limit
            await asyncio.sleep(API_CALL_DELAY)

        # Add delay before next API call
        await asyncio.sleep(API_CALL_DELAY)

        # Fetch closed positions with pagination
        # IMPORTANT: Continue until we get an EMPTY result, not just when len(batch) < limit
        closed_positions = []
        closed_limit = 50  # API max limit
        offset = 0
        max_pages = 500  # Increased to handle users with many closed positions

        for page in range(max_pages):
            batch = await self.data_client.get_closed_positions(
                user=user_address,
                limit=closed_limit,
                offset=offset,
                sort_by="TIMESTAMP",
                sort_direction="DESC",  # Get most recent first for efficiency
            )

            if not batch:
                logger.info(
                    f"Syncing {user_address}: empty result at offset {offset}, "
                    f"total closed positions fetched: {len(closed_positions)}"
                )
                break

            closed_positions.extend(batch)
            logger.info(
                f"Syncing {user_address}: fetched {len(batch)} closed positions "
                f"(offset {offset}, total so far {len(closed_positions)})"
            )

            if len(batch) == 0:
                break  # No more data

            offset += closed_limit

            # Add delay between API calls to respect rate limits
            await asyncio.sleep(API_CALL_DELAY)

            # Safety check for very large datasets
            if offset >= 10000:
                logger.warning(
                    f"Syncing {user_address}: reached max offset {offset}, "
                    "stopping to prevent infinite loop"
                )
                break

        total_upserted = 0

        # First, delete any existing active positions that have corresponding closed positions
        # This prevents unique constraint conflicts when upserting closed positions
        if closed_positions:
            deleted_count = await self.db.delete_active_positions_for_closed(user_address, closed_positions)
            logger.info(f"Deleted {deleted_count} active positions that are now closed for {user_address}")

        # Process active positions - mark status as "active"
        if active_positions:
            for p in active_positions:
                p["status"] = "active"
            new_count = await self.db.upsert_positions(user_address, active_positions)
            total_upserted += new_count

        # Process closed positions - mark status as "closed" and upsert
        if closed_positions:
            for p in closed_positions:
                p["status"] = "closed"
            new_count = await self.db.upsert_positions(user_address, closed_positions)
            total_upserted += new_count

        # Update sync state
        await self.db.upsert_sync_state(
            user_address,
            positions_synced_at=datetime.utcnow(),
            positions_status="completed",
        )

        # Invalidate cache for this address
        await self._invalidate_cache(user_address)

        return {
            "active_positions": len(active_positions),
            "closed_positions": len(closed_positions),
            "total_positions_upserted": total_upserted,
            "status": "completed" if (active_positions or closed_positions) else "no_positions",
        }

    async def _invalidate_cache(self, user_address: str) -> None:
        """Invalidate Redis cache for a user address.

        Clears all cache keys matching the pattern 'account:{address}:*'
        and also 'account:stats:{address}'.
        """
        try:
            from app.core.redis import get_redis
            redis = get_redis()

            # Clear stats cache
            stats_key = f"account:stats:{user_address.lower()}"
            redis.delete(stats_key)
            logger.info(f"Invalidated cache key: {stats_key}")

            # Note: For pattern-based deletion, we'd need SCAN which is not directly
            # available in upstash_redis. We'll rely on TTL-based expiration for
            # other cache keys or clear them explicitly when we find them.
        except Exception as e:
            logger.warning(f"Failed to invalidate cache for {user_address}: {e}")

    async def calculate_pnl_for_address(
        self,
        user_address: str,
        since_days: Optional[int] = None,
    ) -> dict:
        """
        Calculate PnL for a user address.

        Args:
            user_address: Wallet address
            since_days: Optional filter for time period (1, 7, 30, 180, 365)

        Returns:
            dict with PnL breakdown by market and totals
        """
        pnl_by_market = await self.db.calculate_realized_pnl(user_address)

        # Augment with unrealized PnL from stored active positions
        stored_positions = await self.db.get_user_positions(user_address, status="active", limit=5000)
        unrealized_by_market = {}
        for pos in stored_positions:
            cond_id = pos["condition_id"]
            unrealized = pos.get("unrealized_pnl", 0) or 0
            if unrealized_by_market.get(cond_id) is None:
                unrealized_by_market[cond_id] = {
                    "unrealized_pnl": Decimal("0"),
                    "market_title": pos.get("market_title", ""),
                }
            unrealized_by_market[cond_id]["unrealized_pnl"] += Decimal(str(unrealized))

        # Merge unrealized into pnl_by_market
        for cond_id, data in unrealized_by_market.items():
            if cond_id in pnl_by_market:
                pnl_by_market[cond_id]["unrealized_pnl"] = data["unrealized_pnl"]
            else:
                pnl_by_market[cond_id] = {
                    "realized_pnl": Decimal("0"),
                    "cost": Decimal("0"),
                    "proceeds": Decimal("0"),
                    "market_title": data["market_title"],
                    "unrealized_pnl": data["unrealized_pnl"],
                }

        if since_days:
            # Filter trades by timestamp
            cutoff = int((datetime.utcnow() - timedelta(days=since_days)).timestamp())
            trades = await self.db.get_user_trades(user_address, since_timestamp=cutoff)

            # Re-calculate PnL only for trades in the period
            filtered_pnl = {}
            for t in trades:
                cond_id = t["condition_id"]
                if cond_id not in filtered_pnl:
                    filtered_pnl[cond_id] = {
                        "cost": Decimal("0"),
                        "proceeds": Decimal("0"),
                        "market_title": t.get("market_title", ""),
                    }

                size = Decimal(str(t["size"]))
                price = Decimal(str(t["price"]))

                if t["side"] == "BUY":
                    filtered_pnl[cond_id]["cost"] += size * price
                elif t["side"] == "SELL":
                    filtered_pnl[cond_id]["proceeds"] += size * price

            # Calculate net PnL for filtered
            for cond_id, data in filtered_pnl.items():
                data["realized_pnl"] = data["proceeds"] - data["cost"]

            pnl_by_market = filtered_pnl

        # Calculate totals
        total_pnl = Decimal("0")
        total_cost = Decimal("0")
        total_proceeds = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        winning_markets = 0
        losing_markets = 0

        for cond_id, data in pnl_by_market.items():
            realized = data.get("realized_pnl", Decimal("0"))
            unrealized = data.get("unrealized_pnl", Decimal("0")) or Decimal("0")
            total_pnl += realized + unrealized
            total_cost += data.get("cost", Decimal("0"))
            total_proceeds += data.get("proceeds", Decimal("0"))
            total_unrealized_pnl += unrealized

            if realized > 0:
                winning_markets += 1
            elif realized < 0:
                losing_markets += 1

        total_trades = winning_markets + losing_markets
        win_rate = (
            Decimal(str(winning_markets / total_trades * 100))
            if total_trades > 0
            else Decimal("0")
        )

        # Calculate profit factor
        total_profit = sum(
            data["realized_pnl"]
            for data in pnl_by_market.values()
            if data.get("realized_pnl", Decimal("0")) > 0
        )
        total_loss = sum(
            abs(data["realized_pnl"])
            for data in pnl_by_market.values()
            if data.get("realized_pnl", Decimal("0")) < 0
        )
        profit_factor = (
            total_profit / total_loss if total_loss > 0 else Decimal("0")
        )

        return {
            "address": user_address.lower(),
            "period_days": since_days,
            "total_pnl": float(total_pnl),
            "total_realized_pnl": float(total_pnl - total_unrealized_pnl),
            "total_unrealized_pnl": float(total_unrealized_pnl),
            "total_cost": float(total_cost),
            "total_proceeds": float(total_proceeds),
            "winning_markets": winning_markets,
            "losing_markets": losing_markets,
            "total_markets": total_trades,
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "by_market": {
                cond_id: {
                    "realized_pnl": float(data.get("realized_pnl", Decimal("0"))),
                    "unrealized_pnl": float(data.get("unrealized_pnl", Decimal("0")) or Decimal("0")),
                    "cost": float(data.get("cost", Decimal("0"))),
                    "proceeds": float(data.get("proceeds", Decimal("0"))),
                    "market_title": data.get("market_title", ""),
                }
                for cond_id, data in pnl_by_market.items()
            },
        }

    async def calculate_pnl_from_positions(
        self,
        user_address: str,
        since_days: Optional[int] = None,
    ) -> dict:
        """
        Calculate PnL directly from stored positions (with enhanced P/L calculation).

        This method uses the stored realized_pnl and unrealized_pnl values
        from the positions table, which have been calculated based on
        market outcomes (from Gamma API).

        Args:
            user_address: Wallet address
            since_days: Optional filter for time period (not used yet)

        Returns:
            dict with PnL breakdown by market and totals
        """
        # Get all positions from database
        all_positions = await self.db.get_user_positions(user_address, limit=10000)

        # Aggregate P/L by (condition_id, asset_id)
        # Each unique (condition_id, asset_id) represents a different position (Yes or No)
        positions_by_key = {}
        for pos in all_positions:
            cond_id = pos["condition_id"]
            asset_id = pos.get("asset_id", "")
            status = pos.get("status", "")
            key = (cond_id, asset_id)

            if key not in positions_by_key:
                positions_by_key[key] = pos
            else:
                # If position already exists, prefer closed/pending_redeem over active
                # since closed positions have accurate P/L data
                existing_status = positions_by_key[key].get("status", "")
                if status in ("closed", "pending_redeem") and existing_status == "active":
                    positions_by_key[key] = pos

        # Now calculate P/L
        pnl_by_market = {}
        total_realized_pnl = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        total_cost = Decimal("0")
        total_proceeds = Decimal("0")
        winning_markets = 0
        losing_markets = 0

        for (cond_id, asset_id), pos in positions_by_key.items():
            market_title = pos.get("market_title", "")
            realized_pnl = Decimal(str(pos.get("realized_pnl", 0) or 0))
            unrealized_pnl = Decimal(str(pos.get("unrealized_pnl", 0) or 0))
            cost = Decimal(str(pos.get("cost", 0) or 0))
            # Use (condition_id, asset_id) as key for by_market breakdown
            market_key = f"{cond_id}_{asset_id}"

            pnl_by_market[market_key] = {
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "cost": cost,
                "proceeds": Decimal("0"),
                "market_title": market_title,
                "condition_id": cond_id,
                "asset_id": asset_id,
            }

            total_realized_pnl += realized_pnl
            total_unrealized_pnl += unrealized_pnl
            total_cost += cost

            # Count winning/losing markets based on realized P/L
            if realized_pnl > 0:
                winning_markets += 1
            elif realized_pnl < 0:
                losing_markets += 1

        total_pnl = total_realized_pnl + total_unrealized_pnl
        total_trades = winning_markets + losing_markets
        win_rate = (
            Decimal(str(winning_markets / total_trades * 100))
            if total_trades > 0
            else Decimal("0")
        )

        # Calculate profit factor
        total_profit = sum(
            data["realized_pnl"]
            for data in pnl_by_market.values()
            if data.get("realized_pnl", Decimal("0")) > 0
        )
        total_loss = sum(
            abs(data["realized_pnl"])
            for data in pnl_by_market.values()
            if data.get("realized_pnl", Decimal("0")) < 0
        )
        profit_factor = (
            total_profit / total_loss if total_loss > 0 else Decimal("0")
        )

        return {
            "address": user_address.lower(),
            "period_days": since_days,
            "total_pnl": float(total_pnl),
            "total_realized_pnl": float(total_realized_pnl),
            "total_unrealized_pnl": float(total_unrealized_pnl),
            "total_cost": float(total_cost),
            "total_proceeds": float(total_proceeds),
            "winning_markets": winning_markets,
            "losing_markets": losing_markets,
            "total_markets": total_trades,
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "by_market": {
                cond_id: {
                    "realized_pnl": float(data.get("realized_pnl", Decimal("0"))),
                    "unrealized_pnl": float(data.get("unrealized_pnl", Decimal("0"))),
                    "cost": float(data.get("cost", Decimal("0"))),
                    "proceeds": float(data.get("proceeds", Decimal("0"))),
                    "market_title": data.get("market_title", ""),
                }
                for cond_id, data in pnl_by_market.items()
            },
        }

    async def get_pnl_history(
        self,
        user_address: str,
        period: str = "1m",
    ) -> dict:
        """
        Get PnL history as time-series data for charting.

        First tries to get data from Redis cache. If not available or empty,
        falls back to calculating from database.

        Args:
            user_address: Wallet address
            period: Time period (1d, 1w, 1m, 6m, 1y)

        Returns:
            dict with time-series PnL data points
        """
        from app.core.redis import get_redis

        redis = get_redis()

        # Period to days mapping
        period_days_map = {
            "1d": 1,
            "1w": 7,
            "1m": 30,
            "6m": 180,
            "1y": 365,
        }
        days = period_days_map.get(period, 30)
        cutoff = int((datetime.utcnow() - timedelta(days=days)).timestamp())

        # Try to get from Redis first
        try:
            redis_data = get_pnl_history_from_redis(
                redis,
                user_address,
                period,
                start_ts=cutoff,
            )
            if redis_data:
                return {
                    "address": user_address.lower(),
                    "period": period,
                    "data": redis_data,
                }
        except Exception as e:
            logger.warning(f"Failed to get PnL history from Redis for {user_address}: {e}")

        # Fall back to database calculation
        return await self._calculate_pnl_history_from_db(user_address, period, cutoff)

    async def _calculate_pnl_history_from_db(
        self,
        user_address: str,
        period: str,
        cutoff: int,
    ) -> dict:
        """
        Calculate PnL history directly from database (fallback when Redis unavailable).

        Creates data points at FIXED INTERVALS (1 hour for 1D, 3 hours for others),
        with each point showing the P/L of positions that closed within that interval.
        The "midpoint average" means the P/L is the sum/average of positions closed
        in that time window.

        Args:
            user_address: Wallet address
            period: Time period (1d, 1w, 1m, 6m, 1y)
            cutoff: Unix timestamp for the cutoff

        Returns:
            dict with time-series PnL data points
        """
        from datetime import datetime

        period_days_map = {
            "1d": 1,
            "1w": 7,
            "1m": 30,
            "6m": 180,
            "1y": 365,
        }
        days = period_days_map.get(period, 30)

        # Get closed positions for the period
        closed_positions = await self.db.get_user_closed_positions(
            user_address,
            since_timestamp=cutoff,
            limit=10000,
        )

        # Determine bucket size based on period:
        # 1D: last 24 hours, data point every 1 hour
        # 1W/1M/6M/1Y: data point every 3 hours
        if period == "1d":
            bucket_seconds = 3600  # 1 hour
        else:
            bucket_seconds = 10800  # 3 hours

        # Calculate the time range
        now = datetime.utcnow()
        now_ts = int(now.timestamp())

        # Round end_ts to the nearest bucket boundary
        end_ts = (now_ts // bucket_seconds) * bucket_seconds
        # Start from cutoff, rounded to bucket boundary
        start_ts = (cutoff // bucket_seconds) * bucket_seconds

        # Build a map of bucket -> positions that closed in that bucket
        bucket_positions: dict[int, list] = {}
        for pos in closed_positions:
            ts = pos.get("closed_at_timestamp", 0)
            if ts == 0:
                continue
            bucket_key = (ts // bucket_seconds) * bucket_seconds
            if bucket_key not in bucket_positions:
                bucket_positions[bucket_key] = []
            bucket_positions[bucket_key].append(pos)

        # Generate data points for every bucket in the range
        data_points = []
        cumulative = Decimal("0")
        current_ts = start_ts

        while current_ts <= end_ts:
            positions_in_bucket = bucket_positions.get(current_ts, [])

            # Calculate P/L for this bucket (sum of realized_pnl for positions that closed in this bucket)
            bucket_pnl = Decimal("0")
            position_count = len(positions_in_bucket)
            for pos in positions_in_bucket:
                realized_pnl = Decimal(str(pos.get("realized_pnl", 0) or 0))
                bucket_pnl += realized_pnl

            cumulative += bucket_pnl
            data_points.append({
                "timestamp": current_ts,
                "pnl": float(bucket_pnl),  # P/L in this interval (midpoint average = sum)
                "cumulative_pnl": float(cumulative),
                "position_count": position_count,
            })

            current_ts += bucket_seconds

        return {
            "address": user_address.lower(),
            "period": period,
            "data": data_points,
        }

    async def calculate_and_store_pnl_history(
        self,
        user_address: str,
    ) -> dict:
        """
        Calculate PnL history for all periods and store in Redis.

        Called after sync_positions_enhanced to cache the history data.

        Args:
            user_address: Wallet address

        Returns:
            dict with status for each period
        """
        from app.core.redis import get_redis

        redis = get_redis()
        periods = ["1d", "1w", "1m", "6m", "1y"]
        results = {}

        for period in periods:
            try:
                period_days_map = {
                    "1d": 1,
                    "1w": 7,
                    "1m": 30,
                    "6m": 180,
                    "1y": 365,
                }
                days = period_days_map.get(period, 30)
                cutoff = int((datetime.utcnow() - timedelta(days=days)).timestamp())

                # Calculate history from DB
                history_data = await self._calculate_pnl_history_from_db(
                    user_address, period, cutoff
                )

                if history_data["data"]:
                    ttl = get_pnl_history_ttl_seconds(period)
                    store_pnl_history(
                        redis,
                        user_address,
                        period,
                        history_data["data"],
                        ttl_seconds=ttl,
                    )
                    results[period] = {
                        "status": "stored",
                        "data_points": len(history_data["data"]),
                    }
                else:
                    results[period] = {
                        "status": "no_data",
                        "data_points": 0,
                    }
            except Exception as e:
                logger.warning(f"Failed to store PnL history for {user_address}/{period}: {e}")
                results[period] = {
                    "status": "error",
                    "error": str(e),
                }

        return results


    async def sync_positions_enhanced(
        self,
        user_address: str,
        force_refresh: bool = False,
        manage_status: bool = True,
    ) -> dict:
        """
        Enhanced position sync with proper P/L calculation.

        This method:
        1. Acquires distributed sync lock to prevent concurrent syncs
        2. Fetches positions and closed-positions from Data API
        3. Determines status based on percentRealizedPnl and endDate
        4. Calculates correct realized P/L for ended markets
        5. Merges data and updates database
        6. Recalculates total P/L
        7. Updates 10-dimensional score
        8. Updates sync status in Redis (unless manage_status=False)

        Args:
            user_address: Wallet address to sync
            force_refresh: If True, re-fetch all data from scratch
            manage_status: If True, update sync status in Redis (default True).
                          Set to False when called by _background_sync which
                          coordinates status updates across multiple syncs.

        Returns:
            dict with sync results, P/L breakdown, and updated scores
        """
        from app.services.scoring_service import get_address_scores_from_db
        from app.core.redis import acquire_sync_lock, release_sync_lock, set_sync_status

        logger.info(f"Starting enhanced sync for {user_address}")

        # Try to acquire distributed lock
        sync_lock = acquire_sync_lock(user_address)
        if not sync_lock:
            logger.info(f"Could not acquire sync lock for {user_address}, skipping")
            raise Exception("Sync already in progress for this address")

        def _set_status(status: str, progress_percent: int = 0, error: Optional[str] = None, estimated_seconds_remaining: Optional[int] = None):
            if manage_status:
                set_sync_status(user_address, status, progress_percent=progress_percent,
                              estimated_seconds_remaining=estimated_seconds_remaining, error=error)

        try:
            # Update sync status
            _set_status("syncing", progress_percent=5)

            # Step 1: Fetch all positions from /positions API with pagination
            # IMPORTANT: Fetch both regular positions AND redeemable positions
            # Polymarket returns different data for redeemable=True
            active_positions = []
            positions_limit = 1000
            positions_offset = 0
            max_pages = 500  # Increased to handle users with many positions

            _set_status("syncing", progress_percent=10)

            for page in range(max_pages):
                # Fetch regular (non-redeemable) positions
                batch = await self.data_client.get_positions(
                    user=user_address,
                    limit=positions_limit,
                    offset=positions_offset,
                )
                if not batch:
                    logger.info(
                        f"Syncing {user_address}: empty result at offset {positions_offset}, "
                        f"total active positions fetched: {len(active_positions)}"
                    )
                    break
                active_positions.extend(batch)
                logger.info(
                    f"Syncing {user_address}: fetched {len(batch)} active positions "
                    f"(offset {positions_offset}, total {len(active_positions)})"
                )
                if len(batch) == 0:
                    break  # No more data
                positions_offset += positions_limit
                await asyncio.sleep(API_CALL_DELAY)

            await asyncio.sleep(API_CALL_DELAY)

            _set_status("syncing", progress_percent=30)

            # Step 2: Fetch all closed positions with pagination
            # IMPORTANT: The Polymarket API may return fewer items than limit even when more pages exist.
            # We must continue fetching until we get an EMPTY result, not just when len(batch) < limit.
            # Using a high limit (50) to fetch more per page while still detecting pagination boundaries.
            closed_positions = []
            closed_limit = 50
            offset = 0
            max_pages = 500  # Increased to handle users with many closed positions
            last_batch_size = None

            for page in range(max_pages):
                batch = await self.data_client.get_closed_positions(
                    user=user_address,
                    limit=closed_limit,
                    offset=offset,
                    sort_by="TIMESTAMP",
                    sort_direction="DESC",
                )
                if not batch:
                    # Empty result means no more data - pagination is complete
                    logger.info(
                        f"Syncing {user_address}: empty result at offset {offset}, "
                        f"total closed positions fetched: {len(closed_positions)}"
                    )
                    break

                batch_count = len(batch)
                closed_positions.extend(batch)

                # Log progress every page
                logger.info(
                    f"Syncing {user_address}: fetched {batch_count} closed positions "
                    f"(offset {offset}, total {len(closed_positions)})"
                )

                # Only break when we get an EMPTY result (no more pages)
                # Don't break on partial page (batch_count < limit) as API may have variable page sizes
                if batch_count == 0:
                    break

                # Track if we got a full page - if so, there might be more data
                if batch_count < closed_limit:
                    # Partial page - this is likely the last page
                    # But we still need to try next offset to confirm (some APIs are inconsistent)
                    if last_batch_size is not None and last_batch_size < closed_limit:
                        # Got partial page after already getting a partial page - really done
                        break
                last_batch_size = batch_count

                offset += closed_limit
                await asyncio.sleep(API_CALL_DELAY)

            logger.info(f"Fetched {len(active_positions)} active, {len(closed_positions)} closed positions")

            # Step 3: Build a map of condition_id -> closed position for merging
            # When same condition_id appears in both, prefer closed-positions data
            closed_by_condition = {}
            for c in closed_positions:
                cond_id = c.get("conditionId", "")
                if cond_id:
                    closed_by_condition[cond_id] = c

            # Step 4: Process active positions and determine status/P/L
            now = datetime.utcnow()
            processed_positions = []
            pending_redeem_positions = []
            active_condition_ids = set()

            for p in active_positions:
                cond_id = p.get("conditionId", "")
                active_condition_ids.add(cond_id)

                # Parse fields from API
                size = Decimal(str(p.get("size", 0) or 0))
                avg_price = Decimal(str(p.get("avgPrice", 0) or 0))
                cost = size * avg_price
                percent_realized_pnl = p.get("percentRealizedPnl")
                end_date_str = p.get("endDate", "")
                is_redeemable = p.get("redeemable", False)

                # Determine if market has ended
                market_ended = False
                if end_date_str:
                    try:
                        end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                        market_ended = end_dt.replace(tzinfo=None) < now
                    except:
                        pass

                # Determine status based on percentRealizedPnl and market state
                # percentRealizedPnl values:
                # -100 or -99.99 -> market ended with 100% loss
                # 100 -> market ended with 100% win
                status = "active"
                realized_pnl = Decimal("0")
                unrealized_pnl = Decimal(str(p.get("cashPnl", 0) or 0))

                if percent_realized_pnl is not None:
                    prp = float(percent_realized_pnl)
                    if prp == -100 or prp == -99.99:
                        # Market ended with 100% loss
                        # If redeemable=True, user can still redeem (pending_redeem)
                        # If redeemable=False, market has fully settled (closed)
                        if is_redeemable:
                            status = "pending_redeem"
                            realized_pnl = Decimal(str(p.get("cashPnl", 0) or 0))
                            unrealized_pnl = Decimal("0")
                            pending_redeem_positions.append(cond_id)
                        else:
                            status = "closed"
                            realized_pnl = -cost  # Full loss
                            unrealized_pnl = Decimal("0")
                    elif prp == 100:
                        # Market ended with 100% win - pending redeem
                        status = "pending_redeem"
                        realized_pnl = size * (Decimal("1") - avg_price)
                        unrealized_pnl = Decimal("0")  # P/L now realized
                        pending_redeem_positions.append(cond_id)
                    elif market_ended and is_redeemable:
                        # Market ended and redeemable (partial win/loss)
                        status = "pending_redeem"
                        # Use the realizedPnl from API since it accounts for actual outcome
                        realized_pnl = Decimal(str(p.get("realizedPnl", 0) or 0))
                        unrealized_pnl = Decimal("0")
                        pending_redeem_positions.append(cond_id)
                    elif market_ended:
                        # Market ended but not redeemable
                        status = "closed"
                        realized_pnl = Decimal(str(p.get("realizedPnl", 0) or 0))
                        unrealized_pnl = Decimal("0")

                # Build full position dict with ALL fields from API
                # Map API fields to DB fields
                position_dict = {
                    # Core identifiers
                    "condition_id": cond_id,
                    "asset_id": p.get("asset", ""),
                    "user_address": user_address.lower(),

                    # Market info
                    "market_slug": p.get("slug", ""),
                    "market_title": p.get("title", ""),
                    "market_icon": p.get("icon", ""),
                    "outcome": p.get("outcome", ""),
                    "outcome_index": p.get("outcomeIndex"),
                    "event_id": p.get("eventId", ""),
                    "event_slug": p.get("eventSlug", ""),
                    "opposite_outcome": p.get("oppositeOutcome", ""),
                    "opposite_asset": p.get("oppositeAsset", ""),
                    "end_date": end_date_str,

                    # Position details
                    "side": p.get("side") or "",
                    "size": size,
                    "avg_price": avg_price,
                    "cost": cost,
                    "total_bought": Decimal(str(p.get("totalBought", 0) or 0)),
                    "initial_value": Decimal(str(p.get("initialValue", 0) or 0)),
                    "current_value": Decimal(str(p.get("currentValue", 0) or 0)),
                    "cur_price": Decimal(str(p.get("curPrice", 0) or 0)),

                    # Status and P/L
                    "status": status,
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": unrealized_pnl,
                    "percent_realized_pnl": Decimal(str(percent_realized_pnl)) if percent_realized_pnl is not None else None,
                    "percent_pnl": Decimal(str(p.get("percentPnl", 0) or 0)),

                    # Redeem status
                    "redeemable": is_redeemable,
                    "mergeable": p.get("mergeable", False),
                    "negative_risk": p.get("negativeRisk", False),

                    # Timestamps and metadata
                    "trade_count": p.get("tradeCount", 0),
                    "closed_at": None,
                    "source": "positions",

                    # Raw API data - store complete original response
                    "raw_data": dict(p),
                }
                processed_positions.append(position_dict)

            # Step 5: Process closed positions and add to merged list
            # IMPORTANT: Only deduplicate if (condition_id, asset_id) is the same.
            # If condition_id is same but asset_id is different, they are different positions!
            active_key_to_position: dict[tuple, dict] = {}
            for p in processed_positions:
                key = (p["condition_id"], p.get("asset_id", ""))
                active_key_to_position[key] = p

            for c in closed_positions:
                cond_id = c.get("conditionId", "")
                asset_id = c.get("asset", "")

                # Check if this exact (condition_id, asset_id) combination already exists
                key = (cond_id, asset_id)
                if key in active_key_to_position:
                    existing = active_key_to_position[key]
                    # Only update if the existing position is incorrectly "active"
                    # and the closed position has more accurate P/L
                    if existing["status"] == "active":
                        existing["realized_pnl"] = Decimal(str(c.get("realizedPnl", 0) or 0))
                        existing["status"] = "closed"
                        existing["closed_at"] = datetime.fromtimestamp(c.get("timestamp", 0)) if c.get("timestamp") else None
                        logger.info(f"Updated position P/L from closed API for condition_id: {cond_id}, asset_id: {asset_id}")
                    continue

                # Parse closed position data
                realized_pnl = Decimal(str(c.get("realizedPnl", 0) or 0))
                closed_at = datetime.fromtimestamp(c.get("timestamp", 0)) if c.get("timestamp") else None

                # Build full position dict with ALL fields from API
                position_dict = {
                    # Core identifiers
                    "condition_id": cond_id,
                    "asset_id": c.get("asset", ""),
                    "user_address": user_address.lower(),

                    # Market info
                    "market_slug": c.get("slug", ""),
                    "market_title": c.get("title", ""),
                    "market_icon": c.get("icon", ""),
                    "outcome": c.get("outcome", ""),
                    "outcome_index": c.get("outcomeIndex"),
                    "event_id": c.get("eventId", ""),
                    "event_slug": c.get("eventSlug", ""),
                    "opposite_outcome": c.get("oppositeOutcome", ""),
                    "opposite_asset": c.get("oppositeAsset", ""),
                    "end_date": c.get("endDate", ""),

                    # Position details - closed positions don't have size/cost info in API
                    "side": "",
                    "size": Decimal("0"),
                    "avg_price": Decimal(str(c.get("avgPrice", 0) or 0)),
                    "cost": Decimal("0"),
                    "total_bought": Decimal(str(c.get("totalBought", 0) or 0)),
                    "initial_value": Decimal("0"),
                    "current_value": Decimal("0"),
                    "cur_price": Decimal(str(c.get("curPrice", 0) or 0)),

                    # Status and P/L
                    "status": "closed",
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": Decimal("0"),
                    "percent_realized_pnl": None,
                    "percent_pnl": None,

                    # Redeem status
                    "redeemable": False,
                    "mergeable": False,
                    "negative_risk": False,

                    # Timestamps and metadata
                    "trade_count": 0,
                    "closed_at": closed_at,
                    "source": "closed-positions",

                    # Raw API data - store complete original response
                    "raw_data": dict(c),
                }
                processed_positions.append(position_dict)

            # Step 6: Update database with merged positions
            if force_refresh:
                await self.db.delete_all_positions_for_address(user_address)

            # Upsert all processed positions
            total_upserted = await self.db.upsert_positions_enhanced(user_address, processed_positions)

            # Step 7: Calculate total P/L from stored positions
            pnl_data = await self.calculate_pnl_from_positions(user_address)

            # Step 8: Update 10-dimensional score
            active_only = [p for p in processed_positions if p["status"] == "active"]
            scores = await get_address_scores_from_db(
                address=user_address,
                positions=active_only,
            trades=[],
        )

            # Step 9: Invalidate cache
            await self._invalidate_cache(user_address)

            # Step 10: Calculate and store PnL history in Redis
            pnl_history_result = await self.calculate_and_store_pnl_history(user_address)

            # Update sync state
            await self.db.upsert_sync_state(
                user_address,
                positions_synced_at=datetime.utcnow(),
                positions_status="completed",
            )

            # Return result - status management is handled by caller
            return {
                "address": user_address.lower(),
                "active_positions": len([p for p in processed_positions if p["status"] == "active"]),
                "closed_positions": len([p for p in processed_positions if p["status"] == "closed"]),
                "pending_redeem_positions": len(pending_redeem_positions),
                "total_positions_upserted": total_upserted,
                "pnl": pnl_data,
                "scores": {
                    "total_score": scores.total_score,
                    "data_quality": scores.data_quality,
                    "dimensions": scores.to_dict()["dimensions"],
                },
                "pnl_history": pnl_history_result,
                "status": "completed",
            }
        except Exception as e:
            # Update sync status to failed
            _set_status("failed", progress_percent=0, error=str(e))
            raise
        finally:
            # Always release the sync lock
            release_sync_lock(user_address)
            logger.info(f"Released sync lock for {user_address}")


# Singleton
_pnl_service: Optional[PnLService] = None


def get_pnl_service() -> PnLService:
    """Get the PnL service singleton."""
    global _pnl_service
    if _pnl_service is None:
        _pnl_service = PnLService()
    return _pnl_service
