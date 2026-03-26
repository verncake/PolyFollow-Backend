"""
Account Service - P/L Calculation Logic

Handles all profit/loss calculations for trader positions.
All monetary calculations use Decimal for precision.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from dataclasses import dataclass


# Decimal precision context - 6 decimal places for monetary values
MONEY_PRECISION = Decimal("0.000001")
ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass
class PositionPnL:
    """Calculated P/L for a single position."""

    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    pnl_percentage: Decimal  # As a decimal, e.g., 0.05 = 5%


@dataclass
class AccountSummary:
    """Summary of an account's positions and P/L."""

    address: str
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal
    total_pnl: Decimal
    open_positions_count: int
    closed_positions_count: int
    win_rate: Decimal
    profit_factor: Decimal


def calculate_unrealized_pnl(
    side: str,
    size: Decimal,
    entry_price: Decimal,
    current_price: Decimal,
) -> Decimal:
    """
    Calculate unrealized P/L for an open position.

    Unrealized P/L = (Current Price - Entry Price) * Size (for BUY)
                    = (Entry Price - Current Price) * Size (for SELL)

    Args:
        side: "BUY" or "SELL"
        size: Number of shares/contracts
        entry_price: Average fill price at entry
        current_price: Current market price

    Returns:
        Unrealized P/L as Decimal
    """
    if side.upper() == "BUY":
        pnl = (current_price - entry_price) * size
    elif side.upper() == "SELL":
        pnl = (entry_price - current_price) * size
    else:
        raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

    return pnl.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def calculate_realized_pnl(
    side: str,
    size: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
) -> Decimal:
    """
    Calculate realized P/L for a closed position.

    Realized P/L = (Exit Price - Entry Price) * Size (for BUY)
                = (Entry Price - Exit Price) * Size (for SELL)

    Args:
        side: "BUY" or "SELL"
        size: Number of shares/contracts closed
        entry_price: Average fill price at entry
        exit_price: Average fill price at exit

    Returns:
        Realized P/L as Decimal
    """
    if side.upper() == "BUY":
        pnl = (exit_price - entry_price) * size
    elif side.upper() == "SELL":
        pnl = (entry_price - exit_price) * size
    else:
        raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

    return pnl.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def calculate_position_pnl(
    side: str,
    size: Decimal,
    entry_price: Decimal,
    current_price: Decimal,
    exit_price: Optional[Decimal] = None,
) -> PositionPnL:
    """
    Calculate complete P/L for a position.

    Args:
        side: "BUY" or "SELL"
        size: Position size
        entry_price: Average entry price
        current_price: Current market price
        exit_price: Exit price (if closed, None if open)

    Returns:
        PositionPnL with unrealized, realized, and total P/L
    """
    unrealized = calculate_unrealized_pnl(side, size, entry_price, current_price)

    if exit_price is not None:
        realized = calculate_realized_pnl(side, size, entry_price, exit_price)
    else:
        realized = ZERO

    total = unrealized + realized

    # Calculate P/L percentage based on cost basis
    cost_basis = entry_price * size
    if cost_basis > ZERO:
        pnl_percentage = (total / cost_basis).quantize(
            MONEY_PRECISION, rounding=ROUND_HALF_UP
        )
    else:
        pnl_percentage = ZERO

    return PositionPnL(
        unrealized_pnl=unrealized,
        realized_pnl=realized,
        total_pnl=total,
        pnl_percentage=pnl_percentage,
    )


def calculate_win_rate(wins: int, total_trades: int) -> Decimal:
    """
    Calculate win rate as a decimal.

    Args:
        wins: Number of winning trades
        total_trades: Total number of closed trades

    Returns:
        Win rate as decimal (e.g., 0.65 = 65%)
    """
    if total_trades <= 0:
        return ZERO

    win_rate = Decimal(wins) / Decimal(total_trades)
    return win_rate.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def calculate_profit_factor(gross_profit: Decimal, gross_loss: Decimal) -> Decimal:
    """
    Calculate profit factor (ratio of gross profit to gross loss).

    Profit Factor = Gross Profit / |Gross Loss|

    A profit factor > 1 means profitable strategy.
    Values above 1.5 are considered good.

    Args:
        gross_profit: Sum of all winning P/L (positive values)
        gross_loss: Sum of all losing P/L (negative values, passed as absolute)

    Returns:
        Profit factor as Decimal
    """
    if gross_loss == ZERO:
        if gross_profit > ZERO:
            return Decimal("999.999999")  # Very high profit factor
        else:
            return ZERO

    return (gross_profit / gross_loss).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


def calculate_account_summary(
    address: str,
    positions: list[dict],
) -> AccountSummary:
    """
    Calculate complete account summary from a list of positions.

    Args:
        address: Wallet address
        positions: List of position dicts with keys:
            - side: "BUY" or "SELL"
            - size: Position size
            - entry_price: Average entry price
            - current_price: Current price
            - status: "OPEN" or "CLOSED"
            - realized_pnl: Realized P/L (for closed positions)

    Returns:
        AccountSummary with calculated metrics
    """
    total_unrealized = ZERO
    total_realized = ZERO
    open_count = 0
    closed_count = 0
    wins = 0
    total_trades = 0
    gross_profit = ZERO
    gross_loss = ZERO

    for pos in positions:
        side = pos.get("side", "BUY")
        size = Decimal(str(pos.get("size", 0)))
        entry_price = Decimal(str(pos.get("entry_price", 0)))
        current_price = Decimal(str(pos.get("current_price", 0)))
        status = pos.get("status", "OPEN")

        if size <= ZERO or entry_price <= ZERO:
            continue

        if status == "OPEN":
            unrealized = calculate_unrealized_pnl(
                side, size, entry_price, current_price
            )
            total_unrealized += unrealized
            open_count += 1
        else:
            realized = Decimal(str(pos.get("realized_pnl", 0)))
            total_realized += realized
            closed_count += 1
            total_trades += 1

            if realized > ZERO:
                wins += 1
                gross_profit += realized
            elif realized < ZERO:
                gross_loss += abs(realized)

    win_rate = calculate_win_rate(wins, total_trades)
    profit_factor = calculate_profit_factor(gross_profit, gross_loss)

    return AccountSummary(
        address=address,
        total_unrealized_pnl=total_unrealized,
        total_realized_pnl=total_realized,
        total_pnl=total_unrealized + total_realized,
        open_positions_count=open_count,
        closed_positions_count=closed_count,
        win_rate=win_rate,
        profit_factor=profit_factor,
    )
