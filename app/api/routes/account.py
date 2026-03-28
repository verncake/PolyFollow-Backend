"""
Account API routes.

GET /api/v1/account/{address} - Get account summary with P/L
GET /api/v1/account/{address}/positions - Get active positions
GET /api/v1/account/{address}/closed-positions - Get closed positions
GET /api/v1/account/{address}/trades - Get trade history
GET /api/v1/account/{address}/activity - Get activity history
"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from decimal import Decimal

from app.services.data import DataClient, get_data_client
from app.services.gamma import GammaClient, get_gamma_client
from app.services.scoring_service import get_address_scores, get_address_scores_from_db
from app.services.position_enricher import PositionEnricher, EnrichedPosition
from app.services.blockchain import get_blockchain_client
from app.services.pnl_service import get_pnl_service
from app.schemas.schemas import AccountSummaryResponse
from app.core.redis import get_redis, acquire_sync_lock, release_sync_lock, set_sync_status, get_sync_status, set_sync_last_updated, get_sync_last_updated
from app.core.database import get_db_service

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/{address}")
async def get_account_summary(address: str):
    """
    Get comprehensive account summary for a wallet address.

    Returns:
        - Total unrealized P/L
        - Total realized P/L
        - Position counts
        - Win rate
        - Profit factor
        - Score
        - Pending redeem count (positions in closed markets)
        - sync_needed: true if address has no data and sync is needed
        - sync_status: current sync status if sync is needed

    P/L and trading metrics are calculated from synced database data.
    Active positions are fetched from Gamma API for market status enrichment.

    If address has no data in database, returns sync_needed: true and triggers
    background sync using pnl_service.sync_positions_enhanced().
    """
    data_client = get_data_client()
    gamma_client = get_gamma_client()
    pnl_service = get_pnl_service()
    db = get_db_service()

    # Check if address has any data in database
    all_positions = await db.get_user_positions(address, limit=1)
    has_data = len(all_positions) > 0

    # Check sync status from Redis
    redis = get_redis()
    sync_status = get_sync_status(address)
    is_locked = redis.exists(f"sync:lock:{address.lower()}") == 1

    # If no data and not currently syncing, trigger background sync
    if not has_data and not is_locked:
        # Try to acquire lock and trigger sync
        sync_lock = acquire_sync_lock(address)
        if sync_lock:
            # Set initial sync status
            set_sync_status(address, "pending", progress_percent=0)
            # Trigger background sync (fire and forget)
            asyncio.create_task(_background_sync(address, sync_lock))
            # Set status to syncing
            set_sync_status(address, "syncing", progress_percent=10)

    # If no data exists, return early with sync_needed flag
    if not has_data:
        current_sync_status = get_sync_status(address)
        return {
            "address": address.lower(),
            "sync_needed": True,
            "sync_status": current_sync_status.get("status") if current_sync_status else "pending",
            "last_updated": get_sync_last_updated(address),
            "total_unrealized_pnl": "0",
            "total_realized_pnl": "0",
            "total_pnl": "0",
            "open_positions_count": 0,
            "pending_redeem_count": 0,
            "closed_positions_count": 0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": "0",
            "profit_factor": "0",
            "score": 0,
            "data_quality": "insufficient",
            "dimensions": {},
        }

    # Fetch active positions from Gamma API for market status enrichment
    positions = await data_client.get_positions(user=address)

    # Enrich positions with market status from Gamma API
    enricher = PositionEnricher(gamma_client)
    enriched_positions = await enricher.enrich_positions(positions)
    active_positions = enricher.filter_by_status(enriched_positions, "active")

    # Get PnL data from database (uses enhanced positions data if available)
    pnl_data = await pnl_service.calculate_pnl_from_positions(address)

    # Calculate totals from database PnL data
    total_unrealized = Decimal(str(pnl_data.get("total_unrealized_pnl", 0)))
    total_realized = Decimal(str(pnl_data.get("total_realized_pnl", 0)))
    total_pnl = Decimal(str(pnl_data.get("total_pnl", 0)))

    winning_trades = pnl_data.get("winning_markets", 0)
    losing_trades = pnl_data.get("losing_markets", 0)
    total_trades = pnl_data.get("total_markets", 0)
    win_rate = Decimal(str(pnl_data.get("win_rate", 0)))
    profit_factor = Decimal(str(pnl_data.get("profit_factor", 0)))

    # Get position counts from database
    all_positions = await db.get_user_positions(address, limit=10000)
    # closed_positions_count = all non-active positions (closed + pending_redeem)
    closed_positions_count = len([p for p in all_positions if p.get("status") != "active"])
    pending_redeem_count = len([p for p in all_positions if p.get("status") == "pending_redeem"])

    # Get scores from database
    scores = await get_address_scores_from_db(address, positions, [])

    return {
        "address": address.lower(),
        "sync_needed": False,
        "sync_status": None,
        "last_updated": get_sync_last_updated(address),
        "total_unrealized_pnl": str(total_unrealized),
        "total_realized_pnl": str(total_realized),
        "total_pnl": str(total_pnl),
        "open_positions_count": len(active_positions),
        "pending_redeem_count": pending_redeem_count,
        "closed_positions_count": closed_positions_count,
        "total_trades": pnl_data.get("total_markets", 0),
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": str(win_rate),
        "profit_factor": str(profit_factor),
        "score": scores.total_score,
        "data_quality": scores.data_quality,
        "dimensions": scores.to_dict()["dimensions"],
    }


async def _background_sync(address: str, sync_lock):
    """
    Background task to sync address data and release lock when complete.

    Syncs both positions (and 10D score) and activities in sequence:
    - 30%: positions synced
    - 60%: activities synced
    - 90%: 10D score calculated (done within sync_positions_enhanced)
    - 100%: complete
    """
    logger = logging.getLogger(__name__)

    try:
        pnl_service = get_pnl_service()
        set_sync_status(address, "syncing", progress_percent=10)

        # Step 1: Sync positions and calculate 10D score (progress 30%)
        # Pass manage_status=False so we control status updates from here
        result = await pnl_service.sync_positions_enhanced(
            user_address=address,
            force_refresh=False,
            manage_status=False,
        )
        set_sync_status(address, "syncing", progress_percent=30)

        # Step 2: Sync activities (progress 60%)
        await pnl_service.sync_activity_for_address(
            user_address=address,
            force_refresh=False,
        )
        set_sync_status(address, "syncing", progress_percent=90)

        # Step 3: Both syncs done, 10D was calculated in step 1
        # Store last_updated timestamp
        set_sync_last_updated(address)

        set_sync_status(
            address,
            "completed",
            progress_percent=100,
            estimated_seconds_remaining=0,
        )
        logger.info(f"Background sync completed for {address}")
    except Exception as e:
        logger.error(f"Background sync failed for {address}: {e}")
        set_sync_status(
            address,
            "failed",
            progress_percent=0,
            error=str(e),
        )
    finally:
        release_sync_lock(address)


@router.get("/{address}/positions")
async def get_account_positions(
    address: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str = Query("all", description="Filter by status: all, active, closed, pending_redeem"),
    sort_by: Optional[str] = Query(None, description="Sort by: CURRENT, INITIAL, TOKENS, CASHPNL, PERCENTPNL, TITLE, RESOLVING, PRICE, AVGPRICE"),
    sort_direction: str = Query("DESC", description="Sort direction: ASC or DESC"),
):
    """
    Get positions for a wallet address from database.

    Positions are enriched with market status from Gamma API:
    - "active": Market is still open for trading
    - "closed": Market has ended (user already redeemed or no position)
    - "pending_redeem": Market ended but user hasn't redeemed yet
    """
    db = get_db_service()
    gamma_client = get_gamma_client()

    # Read from database
    db_positions = await db.get_user_positions(address, status=status, limit=5000)

    # Build a map of condition_id -> Gamma market data for enrichment
    condition_ids = list(set(p.get("condition_id") for p in db_positions if p.get("condition_id")))
    gamma_market_data = {}
    if condition_ids:
        gamma_markets = await gamma_client.list_markets(limit=min(len(condition_ids), 100))
        for market in gamma_markets:
            cid = market.get("conditionId")
            if cid:
                gamma_market_data[cid] = market

    # Enrich positions with Gamma data
    enriched_positions = []
    for pos in db_positions:
        cond_id = pos.get("condition_id", "")
        gamma_data = gamma_market_data.get(cond_id, {})

        # Use DB status directly as market_status (don't rely on Gamma API for status determination)
        db_status = pos.get("status", "active")
        market_status = db_status

        # Get additional market info from Gamma if available (for display purposes only)
        market_closed = gamma_data.get("closed", False)
        market_resolved = gamma_data.get("resolved", False)
        is_redeemable = gamma_data.get("redeemable", False)

        # Calculate days until end
        end_date = gamma_data.get("endDate") or gamma_data.get("end_date")
        days_until_end = None
        if end_date and not market_closed:
            try:
                if isinstance(end_date, str):
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                else:
                    end_dt = end_date
                delta = end_dt - datetime.now(end_dt.tzinfo)
                days_until_end = delta.days
            except Exception:
                days_until_end = None

        enriched_positions.append({
            **pos.get("raw_data", {}),
            **pos,
            # Explicitly set camelCase aliases for frontend compatibility
            "title": pos.get("market_title") or pos.get("title"),
            "realizedPnl": float(pos.get("realized_pnl")) if pos.get("realized_pnl") is not None else None,
            "totalBought": float(pos.get("total_bought")) if pos.get("total_bought") is not None else None,
            "avgPrice": float(pos.get("avg_price")) if pos.get("avg_price") is not None else None,
            "currentValue": float(pos.get("current_value")) if pos.get("current_value") is not None else None,
            "icon": pos.get("market_icon") or pos.get("icon"),
            "market_status": market_status,
            "market_closed": market_closed,
            "market_resolved": market_resolved,
            "is_redeemable": is_redeemable,
            "days_until_end": days_until_end,
            "display_status": market_status,
        })

    # Sort positions locally if sort_by is specified
    if sort_by:
        reverse = sort_direction == "DESC"
        sort_key_map = {
            "CURRENT": lambda p: float(p.get("current_value", 0) or 0),
            "INITIAL": lambda p: float(p.get("initial_value", 0) or 0),
            "TOKENS": lambda p: float(p.get("size", 0) or 0),
            "CASHPNL": lambda p: float(p.get("realized_pnl", 0) or 0) + float(p.get("unrealized_pnl", 0) or 0),
            "PERCENTPNL": lambda p: float(p.get("percent_pnl", 0) or 0),
            "RESOLVING": lambda p: p.get("days_until_end") if p.get("days_until_end") is not None else 999999,
            "PRICE": lambda p: float(p.get("avg_price", 0) or 0),
            "AVGPRICE": lambda p: float(p.get("avg_price", 0) or 0),
            "TITLE": lambda p: (p.get("market_title") or "").lower(),
        }
        sort_func = sort_key_map.get(sort_by)
        if sort_func:
            enriched_positions.sort(key=sort_func, reverse=reverse)

    # Apply pagination after sorting
    total = len(enriched_positions)
    enriched_positions = enriched_positions[offset:offset + limit]

    pending_redeem_count = len([p for p in enriched_positions if p.get("market_status") == "pending_redeem"])

    return {
        "address": address.lower(),
        "positions": enriched_positions,
        "count": len(enriched_positions),
        "total": total,
        "pending_redeem_count": pending_redeem_count,
        "limit": limit,
        "offset": offset,
        "status_filter": status,
    }


@router.get("/{address}/closed-positions")
async def get_account_closed_positions(
    address: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None, description="Sort by: realizedPnl, market_title, closed_at, TIMESTAMP"),
    sort_direction: str = Query("DESC", description="Sort direction: ASC or DESC"),
):
    """
    Get closed positions for a wallet address from database.
    Returns all non-active positions (closed + pending_redeem).

    Positions are enriched with market status from Gamma API:
    - "closed": Market has ended (user already redeemed)
    - "pending_redeem": Market ended but user hasn't redeemed yet
    """
    db = get_db_service()
    gamma_client = get_gamma_client()

    # Get all non-active positions from database
    all_positions = await db.get_user_positions(address, status="all", limit=10000)
    db_positions = [p for p in all_positions if p.get("status") != "active"]

    # Build a map of condition_id -> Gamma market data for enrichment
    condition_ids = list(set(p.get("condition_id") for p in db_positions if p.get("condition_id")))
    gamma_market_data = {}
    if condition_ids:
        gamma_markets = await gamma_client.list_markets(limit=min(len(condition_ids), 100))
        for market in gamma_markets:
            cid = market.get("conditionId")
            if cid:
                gamma_market_data[cid] = market

    # Pre-fetch activity timestamps for pending_redeem positions
    # This is used for sorting when closed_at is not available
    # Use TRADE activities which have the matching asset_id
    # Batch fetch all at once to avoid N+1 queries
    pending_redeem_activity_timestamps = {}
    pending_redeem_pairs = [
        (pos.get("condition_id", ""), pos.get("asset_id", ""))
        for pos in db_positions
        if pos.get("status") == "pending_redeem" and not pos.get("closed_at")
        and pos.get("condition_id") and pos.get("asset_id")
    ]
    if pending_redeem_pairs:
        activities_map = await db.get_activities_for_conditions(
            user_address=address,
            condition_ids=pending_redeem_pairs,
            activity_type="TRADE",
        )
        for (cond_id, asset_id), activity in activities_map.items():
            if activity and activity.get("timestamp"):
                pending_redeem_activity_timestamps[cond_id] = activity["timestamp"]

    # Enrich positions with Gamma data and spread raw_data
    enriched_positions = []
    for pos in db_positions:
        cond_id = pos.get("condition_id", "")
        gamma_data = gamma_market_data.get(cond_id, {})

        # Determine market status from Gamma
        market_closed = gamma_data.get("closed", False)
        market_resolved = gamma_data.get("resolved", False)
        is_redeemable = gamma_data.get("redeemable", False)

        if market_closed and not market_resolved and is_redeemable:
            market_status = "pending_redeem"
        elif market_closed and market_resolved:
            market_status = "closed"
        elif not market_closed:
            market_status = "active"
        else:
            market_status = pos.get("status", "closed")

        # Calculate days until end
        end_date = gamma_data.get("endDate") or gamma_data.get("end_date")
        days_until_end = None
        if end_date and not market_closed:
            try:
                if isinstance(end_date, str):
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                else:
                    end_dt = end_date
                delta = end_dt - datetime.now(end_dt.tzinfo)
                days_until_end = delta.days
            except Exception:
                days_until_end = None

        # For pending_redeem positions without closed_at, use activity timestamp
        # Use database status (pos.get("status")) instead of Gamma-derived market_status
        # because Gamma may not have market data for all positions
        closed_at_ts = pos.get("closed_at_timestamp")
        db_status = pos.get("status", "")
        if db_status == "pending_redeem" and not closed_at_ts:
            if cond_id in pending_redeem_activity_timestamps:
                closed_at_ts = pending_redeem_activity_timestamps[cond_id]

        # Spread raw_data fields first, then overlay position fields and enrichment
        enriched_positions.append({
            **pos.get("raw_data", {}),
            **pos,
            # Explicitly set camelCase aliases for frontend compatibility
            # These take precedence over raw_data if somehow duplicated
            "title": pos.get("market_title") or pos.get("title"),
            "realizedPnl": float(pos.get("realized_pnl")) if pos.get("realized_pnl") is not None else None,
            "totalBought": float(pos.get("total_bought")) if pos.get("total_bought") is not None else None,
            "avgPrice": float(pos.get("avg_price")) if pos.get("avg_price") is not None else None,
            "currentValue": float(pos.get("current_value")) if pos.get("current_value") is not None else None,
            "icon": pos.get("market_icon") or pos.get("icon"),
            "market_status": market_status,
            "market_closed": market_closed,
            "market_resolved": market_resolved,
            "closed_at_timestamp": closed_at_ts,
            "is_redeemable": is_redeemable,
            "days_until_end": days_until_end,
            "display_status": market_status,
        })

    # Sort positions locally if sort_by is specified
    if sort_by:
        reverse = sort_direction == "DESC"
        sort_key_map = {
            "realizedPnl": lambda p: float(p.get("realized_pnl", 0) or 0),
            "market_title": lambda p: (p.get("market_title") or "").lower(),
            "closed_at": lambda p: p.get("closed_at_timestamp") or 0,
            "TIMESTAMP": lambda p: p.get("closed_at_timestamp") or 0,
        }
        sort_func = sort_key_map.get(sort_by)
        if sort_func:
            enriched_positions.sort(key=sort_func, reverse=reverse)

    # Apply pagination after sorting
    total = len(enriched_positions)
    enriched_positions = enriched_positions[offset:offset + limit]

    pending_redeem_count = len([p for p in enriched_positions if p.get("market_status") == "pending_redeem"])

    return {
        "address": address.lower(),
        "positions": enriched_positions,
        "count": len(enriched_positions),
        "total": total,
        "pending_redeem_count": pending_redeem_count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{address}/trades")
async def get_account_trades(
    address: str,
    market: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get trade history for a wallet address.
    """
    data_client = get_data_client()
    trades = await data_client.get_trades(
        user=address,
        market=market,
        limit=limit,
        offset=offset,
    )

    return {
        "address": address.lower(),
        "trades": trades,
        "count": len(trades),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{address}/activity")
async def get_account_activity(
    address: str,
    activity_type: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get activity history for a wallet address from database.

    Reads activity data from the activities table, which includes:
    - Trades (BUY/SELL)
    - Redemptions (REDEEM)
    - Splits (SPLIT)
    - Merges (MERGE)
    - Rewards (REWARD)

    Supports filtering by activity_type and market (condition_id), with pagination.

    Args:
        address: Wallet address
        activity_type: Filter by type (TRADE, REDEEM, SPLIT, MERGE, REWARD)
        market: Filter by condition_id (market slug)
        limit: Max results per page
        offset: Pagination offset
    """
    db = get_db_service()

    # Map market filter to condition_id if provided
    # The activities table uses condition_id, not market_slug
    condition_id = market if market else None

    # Get activities from database with pagination
    activities = await db.get_user_activities(
        user_address=address,
        activity_type=activity_type,
        condition_id=condition_id,
        limit=limit,
        offset=offset,
    )

    # For backward compatibility, also get trades count from trades table
    total_trades = await db.get_user_trades_count(
        user_address=address,
        market_slug=market,
    )

    return {
        "address": address.lower(),
        "activity": activities,
        "count": len(activities),
        "total_trades": total_trades,
        "limit": limit,
        "offset": offset,
        "activity_type_filter": activity_type,
        "market_filter": market,
    }


@router.get("/{address}/stats")
async def get_account_stats(address: str, refresh: bool = False):
    """
    Get quick stats summary for a wallet address.

    Returns:
        - total_value: Position value from Data API
        - usdc_e_balance: USDC.e balance on Polygon (available for trading)
        - markets_traded_count: Number of markets traded

    Query Params:
        - refresh: If true, bypass cache and fetch fresh data (default: false)
    """
    redis = get_redis()
    cache_key = f"account:stats:{address.lower()}"

    # Try cache first (unless refresh=true)
    if not refresh:
        cached = redis.get(cache_key)
        if cached:
            import json
            data = json.loads(cached)
            data["cached"] = True
            return data

    data_client = get_data_client()
    blockchain_client = get_blockchain_client()

    total_value = await data_client.get_total_value(user=address)
    markets_traded = await data_client.get_markets_traded_count(user=address)

    # Get on-chain USDC.e balance (run in thread to avoid blocking event loop)
    try:
        loop = asyncio.get_event_loop()
        balance = await loop.run_in_executor(None, lambda: blockchain_client.get_usdc_e_balance(address))
        usdc_e = float(balance.formatted_balance)
    except Exception:
        usdc_e = None

    result = {
        "address": address.lower(),
        "total_value": total_value,
        "usdc_e_balance": usdc_e,
        "markets_traded_count": markets_traded,
        "cached": False,
    }

    # Cache for 3 minutes (180 seconds)
    import json
    redis.set(cache_key, json.dumps(result), ex=180)

    return result


@router.post("/{address}/pnl/sync")
async def sync_pnl_data(
    address: str,
    lookback_days: int = Query(365, ge=1, le=365),
    force_refresh: bool = Query(False, description="If true, delete existing trades and re-fetch all from Polymarket"),
):
    """
    Sync trades and calculate PnL from database.

    This endpoint:
    1. Fetches all trades for the address from Gamma API
    2. Stores them in the database for accurate PnL calculation
    3. Returns the calculated PnL breakdown

    Use this to ensure accurate PnL calculation using stored trade data.

    Query Params:
        - lookback_days: Only sync trades within this many days (default: 365)
        - force_refresh: If true, delete existing trades and re-fetch all (default: false)
    """
    pnl_service = get_pnl_service()

    try:
        # Sync positions first (includes cache invalidation)
        positions_sync = await pnl_service.sync_positions_for_address(
            user_address=address,
            force_refresh=force_refresh,
        )

        # Then sync trades
        trades_sync = await pnl_service.sync_trades_for_address(
            user_address=address,
            lookback_days=lookback_days,
            force_refresh=force_refresh,
        )

        # Calculate PnL from stored data
        pnl_data = await pnl_service.calculate_pnl_for_address(
            user_address=address,
        )

        # Invalidate stats cache
        redis = get_redis()
        cache_key = f"account:stats:{address.lower()}"
        redis.delete(cache_key)

        return {
            "address": address.lower(),
            "positions_sync": positions_sync,
            "trades_sync": trades_sync,
            "pnl": pnl_data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{address}/activity/sync")
async def sync_activity_data(
    address: str,
    force_refresh: bool = Query(False, description="If true, delete existing activity and re-fetch all from Polymarket"),
):
    """
    Sync user activity (trades) from Polymarket /activity API.

    This endpoint:
    1. Fetches all activity for the address from Data API with pagination
    2. Stores them in the trades table with full trade details
    3. Activity links to positions via condition_id and asset_id

    Query Params:
        - force_refresh: If true, delete existing activity and re-fetch all (default: false)
    """
    pnl_service = get_pnl_service()

    try:
        result = await pnl_service.sync_activity_for_address(
            user_address=address,
            force_refresh=force_refresh,
        )

        return {
            "address": address.lower(),
            "sync": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{address}/pnl/sync-enhanced")
async def sync_pnl_data_enhanced(
    address: str,
    force_refresh: bool = Query(False, description="If true, delete existing data and re-fetch all from Polymarket"),
):
    """
    Enhanced PnL sync with proper market outcome-based P/L calculation.

    This endpoint:
    1. Fetches positions and closed-positions from Data API
    2. Enriches with Gamma API to get market outcomes
    3. Calculates correct realized P/L based on whether user won or lost
    4. Merges and updates database with correct status and P/L
    5. Recalculates total P/L
    6. Updates 10-dimensional score
    7. Invalidates Redis cache

    Use this for accurate P/L calculation that reflects actual trading outcomes.

    Query Params:
        - force_refresh: If true, delete existing positions and re-fetch all (default: false)
    """
    pnl_service = get_pnl_service()

    try:
        # manage_status=True (default) so sync_positions_enhanced manages its own status
        result = await pnl_service.sync_positions_enhanced(
            user_address=address,
            force_refresh=force_refresh,
        )
        # Manually set completion status since we removed it from sync_positions_enhanced
        set_sync_last_updated(address)
        set_sync_status(address, "completed", progress_percent=100, estimated_seconds_remaining=0)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{address}/pnl")
async def get_pnl(
    address: str,
    period: Optional[str] = Query(None, description="Time period: 1d, 1w, 1m, 6m, 1y, or all"),
):
    """
    Get PnL for a user address.

    Query params:
        - period: Time period filter (1d, 1w, 1m, 6m, 1y, all). Default: all
    """
    # Map period to days
    period_days_map = {
        "1d": 1,
        "1w": 7,
        "1m": 30,
        "6m": 180,
        "1y": 365,
        "all": None,
    }

    since_days = period_days_map.get(period.lower() if period else "all")

    pnl_service = get_pnl_service()

    try:
        pnl_data = await pnl_service.calculate_pnl_from_positions(
            user_address=address,
            since_days=since_days,
        )
        return pnl_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{address}/sync-status")
async def get_address_sync_status(address: str):
    """
    Get sync status for a wallet address.

    Returns the current sync state stored in Redis, including:
    - status: "pending" | "syncing" | "completed" | "failed"
    - progress_percent: 0-100
    - estimated_seconds_remaining: number or null
    - error: error message if status is "failed"

    This endpoint can be polled to track sync progress.
    """
    redis = get_redis()
    is_locked = redis.exists(f"sync:lock:{address.lower()}") == 1
    sync_status = get_sync_status(address)

    # If we have no status but lock exists, sync is in progress
    if not sync_status and is_locked:
        return {
            "status": "syncing",
            "progress_percent": 0,
            "estimated_seconds_remaining": None,
            "error": None,
            "last_updated": None,
        }

    # If no status and no lock, check if address has data
    if not sync_status and not is_locked:
        db = get_db_service()
        positions = await db.get_user_positions(address, limit=1)
        has_data = len(positions) > 0

        if has_data:
            return {
                "status": "completed",
                "progress_percent": 100,
                "estimated_seconds_remaining": 0,
                "error": None,
                "last_updated": get_sync_last_updated(address),
            }
        else:
            return {
                "status": "pending",
                "progress_percent": 0,
                "estimated_seconds_remaining": None,
                "error": None,
                "last_updated": None,
            }

    return {
        "status": sync_status.get("status", "pending"),
        "progress_percent": sync_status.get("progress_percent", 0),
        "estimated_seconds_remaining": sync_status.get("estimated_seconds_remaining"),
        "error": sync_status.get("error"),
        "last_updated": get_sync_last_updated(address),
    }


@router.post("/{address}/sync")
async def trigger_address_sync(address: str):
    """
    Manually trigger sync for a wallet address.

    This endpoint:
    1. Checks if sync is already in progress (returns error if locked)
    2. Triggers background sync via pnl_service.sync_positions_enhanced()
    3. Returns immediately with sync status

    The 15-minute cooldown is enforced client-side. This endpoint just triggers
    the sync and returns the current status.
    """
    redis = get_redis()

    # Check if already syncing
    is_locked = redis.exists(f"sync:lock:{address.lower()}") == 1
    if is_locked:
        return {
            "status": "syncing",
            "progress_percent": 0,
            "estimated_seconds_remaining": None,
            "error": None,
            "last_updated": get_sync_last_updated(address),
        }

    # Try to acquire lock and trigger sync
    sync_lock = acquire_sync_lock(address)
    if not sync_lock:
        return {
            "status": "syncing",
            "progress_percent": 0,
            "estimated_seconds_remaining": None,
            "error": "Sync already in progress",
            "last_updated": get_sync_last_updated(address),
        }

    # Trigger background sync
    set_sync_status(address, "syncing", progress_percent=5)
    asyncio.create_task(_background_sync(address, sync_lock))

    return {
        "status": "syncing",
        "progress_percent": 5,
        "estimated_seconds_remaining": None,
        "error": None,
        "last_updated": get_sync_last_updated(address),
        "manual_sync": True,
    }
