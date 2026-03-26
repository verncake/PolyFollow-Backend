"""
Account API routes.

GET /api/v1/account/{address} - Get account summary with P/L
GET /api/v1/account/{address}/positions - Get active positions
GET /api/v1/account/{address}/closed-positions - Get closed positions
GET /api/v1/account/{address}/trades - Get trade history
GET /api/v1/account/{address}/activity - Get activity history
"""
import asyncio
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from decimal import Decimal

from app.services.data import DataClient, get_data_client
from app.services.gamma import GammaClient, get_gamma_client
from app.services.scoring_service import get_address_scores
from app.services.position_enricher import PositionEnricher, EnrichedPosition
from app.services.blockchain import get_blockchain_client
from app.schemas.schemas import AccountSummaryResponse

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
    """
    data_client = get_data_client()
    gamma_client = get_gamma_client()

    # Fetch positions and trades in parallel
    positions, closed_positions, trades = await asyncio.gather(
        data_client.get_positions(user=address),
        data_client.get_closed_positions(user=address),
        data_client.get_trades(user=address),
    )

    # Enrich positions with market status from Gamma API
    enricher = PositionEnricher(gamma_client)
    enriched_positions = await enricher.enrich_positions(positions)
    pending_redeem_count = enricher.get_pending_redeem_count(enriched_positions)

    # Calculate totals (use enriched positions for accurate counts)
    total_unrealized = Decimal("0")
    total_realized = Decimal("0")
    winning_trades = 0
    losing_trades = 0

    # Only count "active" positions as truly open for P/L
    active_positions = enricher.filter_by_status(enriched_positions, "active")
    for p in active_positions:
        total_unrealized += Decimal(str(p.original.get("cashPnl", 0)))

    for p in closed_positions:
        pnl = Decimal(str(p.get("realizedPnl", 0)))
        total_realized += pnl
        if pnl > 0:
            winning_trades += 1
        elif pnl < 0:
            losing_trades += 1

    total_trades = winning_trades + losing_trades
    win_rate = Decimal(str(winning_trades / total_trades * 100)) if total_trades > 0 else Decimal("0")

    # Calculate profit factor
    total_profit = sum(Decimal(str(p.get("realizedPnl", 0))) for p in closed_positions if p.get("realizedPnl", 0) > 0)
    total_loss = sum(abs(Decimal(str(p.get("realizedPnl", 0)))) for p in closed_positions if p.get("realizedPnl", 0) < 0)
    profit_factor = total_profit / total_loss if total_loss > 0 else Decimal("0")

    # Calculate 10-dimension score
    scores = get_address_scores(address, positions, closed_positions, trades)

    return {
        "address": address.lower(),
        "total_unrealized_pnl": str(total_unrealized),
        "total_realized_pnl": str(total_realized),
        "total_pnl": str(total_unrealized + total_realized),
        "open_positions_count": len(active_positions),
        "pending_redeem_count": pending_redeem_count,
        "closed_positions_count": len(closed_positions),
        "total_trades": len(trades),
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": str(win_rate),
        "profit_factor": str(profit_factor),
        "score": scores.total_score,
        "data_quality": scores.data_quality,
        "dimensions": scores.to_dict()["dimensions"],
    }


@router.get("/{address}/positions")
async def get_account_positions(
    address: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str = Query("all", description="Filter by status: all, active, closed, pending_redeem"),
):
    """
    Get active (open) positions for a wallet address.

    Positions are enriched with market status from Gamma API:
    - "active": Market is still open for trading
    - "closed": Market has ended (user already redeemed or no position)
    - "pending_redeem": Market ended but user hasn't redeemed yet
    """
    data_client = get_data_client()
    gamma_client = get_gamma_client()

    positions = await data_client.get_positions(
        user=address,
        limit=limit,
        offset=offset,
    )

    # Enrich positions with market status
    enricher = PositionEnricher(gamma_client)
    enriched_positions = await enricher.enrich_positions(positions)

    # Filter by status if requested
    if status != "all":
        enriched_positions = enricher.filter_by_status(enriched_positions, status)

    # Convert to dict format for JSON response
    enriched_data = [
        {
            **pos.original,
            "market_status": pos.market_status,
            "market_closed": pos.market_closed,
            "market_resolved": pos.market_resolved,
            "is_redeemable": pos.is_redeemable,
            "days_until_end": pos.days_until_end,
            "display_status": pos.display_status,
        }
        for pos in enriched_positions
    ]

    return {
        "address": address.lower(),
        "positions": enriched_data,
        "count": len(enriched_data),
        "pending_redeem_count": enricher.get_pending_redeem_count(enriched_positions),
        "limit": limit,
        "offset": offset,
        "status_filter": status,
    }


@router.get("/{address}/closed-positions")
async def get_account_closed_positions(
    address: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Get closed (settled) positions for a wallet address.
    """
    data_client = get_data_client()
    positions = await data_client.get_closed_positions(
        user=address,
        limit=limit,
        offset=offset,
    )

    return {
        "address": address.lower(),
        "positions": positions,
        "count": len(positions),
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
    Get activity history for a wallet address.

    Activity types: TRADE, REDEEM, TRANSFER, etc.
    """
    data_client = get_data_client()
    activity = await data_client.get_activity(
        user=address,
        market=market,
        activity_type=activity_type,
        limit=limit,
        offset=offset,
    )

    return {
        "address": address.lower(),
        "activity": activity,
        "count": len(activity),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{address}/stats")
async def get_account_stats(address: str):
    """
    Get quick stats summary for a wallet address.

    Returns:
        - total_value: Position value from Data API
        - usdc_e_balance: USDC.e balance on Polygon (available for trading)
        - markets_traded_count: Number of markets traded
    """
    data_client = get_data_client()
    blockchain_client = get_blockchain_client()

    total_value = await data_client.get_total_value(user=address)
    markets_traded = await data_client.get_markets_traded_count(user=address)

    # Get on-chain USDC.e balance (synchronous web3 call)
    try:
        balance = blockchain_client.get_usdc_e_balance(address)
        usdc_e = float(balance.formatted_balance)
    except Exception:
        usdc_e = None

    return {
        "address": address.lower(),
        "total_value": total_value,
        "usdc_e_balance": usdc_e,
        "markets_traded_count": markets_traded,
    }
