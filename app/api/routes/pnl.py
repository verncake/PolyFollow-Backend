"""
PnL History API routes.

GET /api/v1/pnl/history?address={address}&timeframe={timeframe}

Timeframe rules:
- 1D (Past Day): 24 hours, bucket = 1 hour (24 points)
- 1W (Past Week): 7 days, bucket = 3 hours (56 points)
- 1M (Past Month): 30 days, bucket = 1 day (30 points)
- 6M (Past 6 Months): bucket = 1 week
- 1Y (Past Year): bucket = 1 week or half-month
- ALL: Dynamic bucket based on user's trading history, 50-100 points

PnL Calculation (Simplified Cash Flow Method):
For each time bucket Ti:
- Calculate cumulative deposits (cost of BUY trades)
- Calculate cumulative withdrawals (proceeds from SELL + redemptions)
- PnL at Ti = cumulative withdrawals - cumulative deposits
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_db_service
from app.schemas.schemas import ErrorResponse

router = APIRouter(prefix="/pnl", tags=["pnl"])

# Decimal precision for monetary values
MONEY_PRECISION = Decimal("0.000001")
ZERO = Decimal("0")

# Timeframe configuration
TIMEFRAME_CONFIG = {
    "1D": {"days": 1, "bucket_hours": 1, "description": "Past Day"},
    "1W": {"days": 7, "bucket_hours": 3, "description": "Past Week"},
    "1M": {"days": 30, "bucket_hours": 24, "description": "Past Month"},
    "6M": {"days": 180, "bucket_hours": 168, "description": "Past 6 Months"},  # 168 hours = 1 week
    "1Y": {"days": 365, "bucket_hours": 168, "description": "Past Year"},  # 168 hours = 1 week
    "ALL": {"days": None, "bucket_hours": None, "description": "All Time"},
}

VALID_TIMEFRAMES = list(TIMEFRAME_CONFIG.keys())


def get_bucket_seconds(timeframe: str, user_trade_count: int = 0) -> int:
    """Get bucket size in seconds for the given timeframe."""
    if timeframe == "ALL":
        # Dynamic bucket: aim for 50-100 points based on trading history
        # Estimate based on trade count (each trade has a timestamp)
        if user_trade_count >= 5000:
            # High activity: use half-month buckets (~432 hours)
            return 432 * 3600
        elif user_trade_count >= 1000:
            # Medium activity: use weekly buckets
            return 168 * 3600
        else:
            # Low activity: use daily buckets
            return 24 * 3600
    else:
        config = TIMEFRAME_CONFIG.get(timeframe.upper())
        if config:
            return config["bucket_hours"] * 3600
        return 24 * 3600  # Default to 1 day


def get_start_timestamp(timeframe: str, days: Optional[int] = None) -> int:
    """Get the start timestamp for the given timeframe."""
    if timeframe.upper() == "ALL":
        # For ALL, use a very old cutoff (5 years) or 0 to get all trades
        return 0
    else:
        config = TIMEFRAME_CONFIG.get(timeframe.upper())
        if config and config["days"]:
            cutoff = datetime.utcnow() - timedelta(days=config["days"])
            return int(cutoff.timestamp())
        elif days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            return int(cutoff.timestamp())
        # Default to 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        return int(cutoff.timestamp())


async def resample_pnl_data(
    address: str,
    timeframe: str,
) -> dict:
    """
    Calculate PnL history using positions data with realized_pnl.

    For each time bucket Ti:
    - Get all positions that were closed (status=closed or pending_redeem) up to Ti
    - Sum their realized_pnl as the PnL at that point

    Args:
        address: Wallet address
        timeframe: Time period (1D, 1W, 1M, 6M, 1Y, ALL)

    Returns:
        dict with timeframe, current_pnl, and data points array
    """
    db = get_db_service()
    timeframe = timeframe.upper()

    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"Invalid timeframe: {timeframe}. Must be one of {VALID_TIMEFRAMES}")

    # Get all positions from database (include closed and pending_redeem)
    all_positions = await db.get_user_positions(
        user_address=address,
        status="all",
        limit=100000,
    )

    if not all_positions:
        return {
            "timeframe": timeframe,
            "current_pnl": 0.0,
            "data": [],
        }

    # Filter positions that have closed or pending_redeem status
    # For closed: use closed_at
    # For pending_redeem without closed_at: use activity timestamp as proxy
    closed_positions = []

    # Pre-fetch all activities for pending_redeem positions in a single batch query
    # to avoid N+1 queries inside the loop
    pending_redeem_pairs = [
        (p.get("condition_id", ""), p.get("asset_id", ""))
        for p in all_positions
        if p.get("status") == "pending_redeem" and not p.get("closed_at")
        and p.get("condition_id") and p.get("asset_id")
    ]
    activities_map = {}
    if pending_redeem_pairs:
        activities_map = await db.get_activities_for_conditions(
            user_address=address,
            condition_ids=pending_redeem_pairs,
            activity_type="REDEEM",
        )

    for p in all_positions:
        status = p.get("status")
        if status in ("closed", "pending_redeem"):
            closed_at = p.get("closed_at")
            if not closed_at:
                # For pending_redeem, try to get proxy timestamp from activity data
                # This is more accurate than updated_at since it reflects when the market actually ended
                condition_id = p.get("condition_id", "")
                asset_id = p.get("asset_id", "")
                activity_timestamp = None

                if condition_id and asset_id:
                    # Look up pre-fetched activity from batch query
                    activity = activities_map.get((condition_id, asset_id))
                    if activity and activity.get("timestamp"):
                        activity_timestamp = activity["timestamp"]

                if activity_timestamp:
                    # Use activity timestamp as proxy closed_at
                    try:
                        closed_at = datetime.utcfromtimestamp(activity_timestamp)
                    except Exception:
                        # Fall back to updated_at if timestamp is invalid
                        updated_at = p.get("updated_at")
                        if updated_at:
                            if isinstance(updated_at, str):
                                try:
                                    closed_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                                    closed_at = closed_at.replace(tzinfo=None)
                                except Exception:
                                    continue
                            else:
                                closed_at = updated_at
                        else:
                            continue
                else:
                    # Fall back to updated_at if no activity found
                    updated_at = p.get("updated_at")
                    if updated_at:
                        if isinstance(updated_at, str):
                            try:
                                closed_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                                closed_at = closed_at.replace(tzinfo=None)
                            except Exception:
                                continue
                        else:
                            closed_at = updated_at
                    else:
                        continue
            else:
                if isinstance(closed_at, str):
                    try:
                        closed_at = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                        closed_at = closed_at.replace(tzinfo=None)
                    except Exception:
                        continue
            closed_positions.append({**p, "_calculated_closed_at": closed_at})

    if not closed_positions:
        return {
            "timeframe": timeframe,
            "current_pnl": 0.0,
            "data": [],
        }

    # Sort by calculated closed_at ascending
    closed_positions_sorted = sorted(
        closed_positions,
        key=lambda p: p.get("_calculated_closed_at") or datetime.min
    )

    # Determine start timestamp based on timeframe
    start_ts = get_start_timestamp(timeframe)

    # Determine bucket size
    bucket_seconds = get_bucket_seconds(timeframe, len(closed_positions_sorted))

    # Calculate the time range
    now = datetime.utcnow()
    now_ts = int(now.timestamp())

    # For ALL timeframe, use first position's closed_at as start
    if timeframe == "ALL":
        first_closed = closed_positions_sorted[0].get("_calculated_closed_at")
        if first_closed:
            start_ts = int(first_closed.timestamp())

    # Round end_ts to the nearest bucket boundary
    end_ts = (now_ts // bucket_seconds) * bucket_seconds
    # Start from start_ts, rounded to bucket boundary
    start_bucket_ts = (start_ts // bucket_seconds) * bucket_seconds

    # Generate data points
    data_points = []
    cumulative_pnl = ZERO  # Cumulative realized PnL
    current_ts = start_bucket_ts

    while current_ts <= end_ts:
        # Find all positions with _calculated_closed_at < current bucket end time
        bucket_end_ts = current_ts + bucket_seconds
        positions_up_to_bucket = [
            p for p in closed_positions_sorted
            if p.get("_calculated_closed_at") and p["_calculated_closed_at"].timestamp() < bucket_end_ts
        ]

        # Sum realized_pnl for all positions closed up to this bucket
        cumulative_pnl = sum(
            (Decimal(str(p.get("realized_pnl", 0) or 0)) for p in positions_up_to_bucket),
            ZERO
        )

        # Format timestamp as ISO string
        ts_datetime = datetime.utcfromtimestamp(current_ts)
        ts_iso = ts_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

        data_points.append({
            "timestamp": ts_iso,
            "pnl": float(cumulative_pnl.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)),
        })

        current_ts += bucket_seconds

    # Calculate current PnL (total of all closed + pending_redeem positions)
    current_pnl = sum(
        Decimal(str(p.get("realized_pnl", 0) or 0))
        for p in closed_positions_sorted
    )
    current_pnl = float(current_pnl.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP))

    return {
        "timeframe": timeframe,
        "current_pnl": current_pnl,
        "data": data_points,
    }


@router.get("/history")
async def get_pnl_history(
    address: str,
    timeframe: str = Query("1W", description="Time period: 1D, 1W, 1M, 6M, 1Y, ALL"),
):
    """
    Get PnL history as time-series data for charting.

    Uses the Simplified Cash Flow Method:
    - PnL = cumulative withdrawals (SELL proceeds) - cumulative deposits (BUY costs)

    Query params:
        - address: Wallet address
        - timeframe: Time period (1D, 1W, 1M, 6M, 1Y, ALL)

    Response format:
    ```json
    {
      "timeframe": "1W",
      "current_pnl": -8.31,
      "data": [
        { "timestamp": "2026-03-20T02:00:00Z", "pnl": -2.10 },
        { "timestamp": "2026-03-20T05:00:00Z", "pnl": -3.50 }
      ]
    }
    ```
    """
    try:
        result = await resample_pnl_data(address, timeframe)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate PnL history: {str(e)}")
