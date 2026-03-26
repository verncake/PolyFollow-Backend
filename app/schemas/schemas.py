"""
Pydantic schemas for API request/response validation.

All monetary fields use Decimal for precision.
"""
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MarketSchema(BaseModel):
    """Schema for a Polymarket market."""

    id: str
    question: str
    condition_id: str
    slug: str
    end_date: Optional[str] = Field(None, alias="endDate")
    category: Optional[str] = None
    volume: Optional[str] = None
    liquidity: Optional[str] = None
    outcomes: Optional[str] = None
    outcome_prices: Optional[str] = Field(None, alias="outcomePrices")
    active: Optional[bool] = None
    closed: Optional[bool] = None

    class Config:
        populate_by_name = True


class PositionSchema(BaseModel):
    """Schema for a trading position."""

    id: str
    market_id: str = Field(alias="marketId")
    condition_id: str = Field(alias="conditionId")
    side: str  # "BUY" or "SELL"
    size: Decimal
    entry_price: Decimal = Field(alias="entryPrice")
    current_price: Decimal = Field(alias="currentPrice")
    avg_fill_price: Decimal = Field(alias="avgFillPrice")

    # P/L fields
    unrealized_pnl: Decimal = Field(alias="unrealizedPnl", default=Decimal("0"))
    realized_pnl: Decimal = Field(alias="realizedPnl", default=Decimal("0"))
    total_pnl: Decimal = Field(alias="totalPnl", default=Decimal("0"))

    # Status
    status: str = "OPEN"  # "OPEN" or "CLOSED"
    opened_at: Optional[datetime] = Field(None, alias="openedAt")
    closed_at: Optional[datetime] = Field(None, alias="closedAt")

    class Config:
        populate_by_name = True


class TradeSchema(BaseModel):
    """Schema for a trade."""

    id: str
    market_id: str = Field(alias="marketId")
    condition_id: str = Field(alias="conditionId")
    side: str
    size: Decimal
    price: Decimal
    filled_qty: Decimal = Field(alias="filledQty")
    fees: Decimal = Decimal("0")
    transaction_hash: str = Field(alias="transactionHash")
    block_number: int = Field(alias="blockNumber")
    timestamp: datetime

    class Config:
        populate_by_name = True


class AccountSummaryResponse(BaseModel):
    """Response schema for account summary endpoint."""

    address: str
    total_unrealized_pnl: Decimal = Field(alias="totalUnrealizedPnl")
    total_realized_pnl: Decimal = Field(alias="totalRealizedPnl")
    total_pnl: Decimal = Field(alias="totalPnl")
    open_positions_count: int = Field(alias="openPositionsCount")
    closed_positions_count: int = Field(alias="closedPositionsCount")
    win_rate: Decimal = Field(alias="winRate")
    profit_factor: Decimal = Field(alias="profitFactor")

    class Config:
        populate_by_name = True


class LeaderboardEntry(BaseModel):
    """Schema for a leaderboard entry."""

    rank: int
    address: str
    score: int
    win_rate: Decimal = Field(alias="winRate")
    profit_factor: Decimal = Field(alias="profitFactor")
    total_trades: int = Field(alias="totalTrades")
    total_pnl: Decimal = Field(alias="totalPnl")
    last_updated: datetime = Field(alias="lastUpdated")

    class Config:
        populate_by_name = True


class LeaderboardResponse(BaseModel):
    """Response schema for leaderboard endpoint."""

    entries: list[LeaderboardEntry]
    total_count: int = Field(alias="totalCount")
    cached: bool = False
    cache_ttl: Optional[int] = Field(None, alias="cacheTtl")

    class Config:
        populate_by_name = True


class HealthResponse(BaseModel):
    """Response schema for health check."""

    status: str
    redis: bool
    supabase: bool = True
    polymarket_api: bool = Field(alias="polymarketAPI")

    class Config:
        populate_by_name = True


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    message: str
    status_code: int = Field(alias="statusCode")

    class Config:
        populate_by_name = True
