"""
Position Enricher Service.

Cross-references positions with Gamma API to determine accurate position status.
Handles the case where a market has ended (closed/resolved) but user hasn't redeemed.
"""
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EnrichedPosition:
    """Position with enriched market status."""
    original: Dict[str, Any]
    market_status: str  # "active", "closed", "pending_redeem"
    market_closed: bool
    market_resolved: bool
    is_redeemable: bool
    days_until_end: Optional[int]  # None if ended

    @property
    def display_status(self) -> str:
        """Human-readable status for UI."""
        if self.market_status == "pending_redeem":
            return "Pending Redeem"
        if self.market_status == "closed":
            return "Redeemed"
        return "Active"


class PositionEnricher:
    """
    Enrich positions with market status from Gamma API.

    Polymarket positions remain "Active" in the API even after market ends,
    as users must manually redeem their tokens. This service fixes that.
    """

    # Thresholds for status determination
    REDEEMABLE_BUFFER_DAYS = 1  # Consider redeemable 1 day after end

    def __init__(self, gamma_client):
        """
        Initialize with Gamma API client.

        Args:
            gamma_client: GammaClient instance
        """
        self.gamma_client = gamma_client

    async def enrich_positions(
        self,
        positions: List[Dict[str, Any]],
        market_slugs: Optional[List[str]] = None,
    ) -> List[EnrichedPosition]:
        """
        Enrich positions with market status.

        Args:
            positions: List of position dicts from Data API
            market_slugs: Optional list of slugs to fetch (faster)

        Returns:
            List of EnrichedPosition with accurate status
        """
        if not positions:
            return []

        # Get unique market slugs from positions
        slugs = market_slugs or list(set(
            p.get("slug") for p in positions if p.get("slug")
        ))

        # Batch fetch market statuses
        market_statuses = await self._fetch_market_statuses(slugs)

        # Enrich each position
        enriched = []
        for pos in positions:
            slug = pos.get("slug")
            market_info = market_statuses.get(slug, {})

            enriched_pos = self._enrich_single_position(pos, market_info)
            enriched.append(enriched_pos)

        return enriched

    async def _fetch_market_statuses(
        self,
        slugs: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch market statuses in batch using parallel requests.

        Returns:
            Dict mapping slug -> market info with status fields
        """
        statuses = {}

        async def fetch_single(slug: str) -> tuple[str, Dict[str, Any]]:
            """Fetch a single market and return slug -> status mapping."""
            try:
                market = await self.gamma_client.get_market_by_slug(slug)
                if market:
                    return slug, {
                        "closed": market.get("closed", False),
                        "active": market.get("active", False),
                        "accepting_orders": market.get("acceptingOrders", True),
                        "end_date": market.get("endDate"),
                        "last_trade_price": market.get("lastTradePrice"),
                    }
            except Exception:
                pass
            # If we can't fetch, assume active
            return slug, {
                "closed": False,
                "active": True,
                "accepting_orders": True,
                "end_date": None,
                "last_trade_price": None,
            }

        # Fetch all in parallel
        results = await asyncio.gather(*[fetch_single(slug) for slug in slugs])

        for slug, status in results:
            statuses[slug] = status

        return statuses

    def _enrich_single_position(
        self,
        position: Dict[str, Any],
        market_info: Dict[str, Any]
    ) -> EnrichedPosition:
        """Enrich a single position with market status."""

        # Parse end date
        end_date_str = market_info.get("end_date") or position.get("endDate")
        days_until_end = None
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                delta = end_date - datetime.now()
                days_until_end = delta.days
            except Exception:
                days_until_end = None

        # Determine status
        market_closed = market_info.get("closed", False)
        market_active = market_info.get("active", True)
        is_redeemable = position.get("redeemable", False)

        if market_closed:
            # Market has ended
            if is_redeemable:
                market_status = "pending_redeem"
            else:
                market_status = "closed"
        else:
            market_status = "active"

        return EnrichedPosition(
            original=position,
            market_status=market_status,
            market_closed=market_closed,
            market_resolved=market_closed,  # closed implies resolved
            is_redeemable=is_redeemable,
            days_until_end=days_until_end,
        )

    def filter_by_status(
        self,
        positions: List[EnrichedPosition],
        status: str,
    ) -> List[EnrichedPosition]:
        """
        Filter positions by status.

        Args:
            positions: List of EnrichedPosition
            status: "active", "closed", "pending_redeem", or "all"

        Returns:
            Filtered list
        """
        if status == "all":
            return positions
        return [p for p in positions if p.market_status == status]

    def get_pending_redeem_count(
        self,
        positions: List[EnrichedPosition]
    ) -> int:
        """Get count of positions pending redeem."""
        return len([p for p in positions if p.market_status == "pending_redeem"])
