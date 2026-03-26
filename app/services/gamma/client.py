"""
Gamma API Client for Polymarket.

Handles public market data: Events, Markets, Tags, Series, Comments, Profiles, Search.
"""
from typing import Optional, Any
from app.services.base import BasePolymarketClient, PolymarketAPIError


class GammaClient(BasePolymarketClient):
    """
    Async client for Polymarket Gamma API.

    Base URL: https://gamma-api.polymarket.com
    """

    def __init__(self):
        super().__init__("https://gamma-api.polymarket.com")

    # ====================
    # Events API
    # ====================

    async def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        with_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """
        List all events.

        Args:
            limit: Max number of events to return
            offset: Pagination offset
            with_deleted: Include deleted events

        Returns:
            List of event objects
        """
        url = self._build_url("/events")
        params = {
            "limit": limit,
            "offset": offset,
            "withDeleted": with_deleted,
        }
        return await self._request_with_retry("GET", url, params=params)

    async def get_event_by_id(self, event_id: str) -> Optional[dict[str, Any]]:
        """
        Get a specific event by ID.

        Args:
            event_id: The event ID

        Returns:
            Event object or None if not found
        """
        url = self._build_url(f"/events/{event_id}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_event_by_slug(self, slug: str) -> Optional[dict[str, Any]]:
        """
        Get a specific event by slug.

        Args:
            slug: The event slug

        Returns:
            Event object or None if not found
        """
        url = self._build_url(f"/events/slug/{slug}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_event_tags(self, event_id: str) -> list[dict[str, Any]]:
        """
        Get tags for an event.

        Args:
            event_id: The event ID

        Returns:
            List of tag objects
        """
        url = self._build_url(f"/events/{event_id}/tags")
        return await self._request_with_retry("GET", url)

    # ====================
    # Markets API
    # ====================

    async def list_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        closed: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        List all markets.

        Args:
            limit: Max number of markets to return
            offset: Pagination offset
            closed: Filter by closed status

        Returns:
            List of market objects
        """
        url = self._build_url("/markets")
        params = {"limit": limit, "offset": offset}
        if closed is not None:
            params["closed"] = closed
        return await self._request_with_retry("GET", url, params=params)

    async def get_market_by_id(self, market_id: str) -> Optional[dict[str, Any]]:
        """
        Get a specific market by ID.

        Args:
            market_id: The market ID

        Returns:
            Market object or None if not found
        """
        url = self._build_url(f"/markets/{market_id}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_market_by_slug(self, slug: str) -> Optional[dict[str, Any]]:
        """
        Get a specific market by slug.

        Args:
            slug: The market slug

        Returns:
            Market object or None if not found
        """
        url = self._build_url(f"/markets/slug/{slug}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_market_tags(self, market_id: str) -> list[dict[str, Any]]:
        """
        Get tags for a market.

        Args:
            market_id: The market ID

        Returns:
            List of tag objects
        """
        url = self._build_url(f"/markets/{market_id}/tags")
        return await self._request_with_retry("GET", url)

    async def search_markets(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Search markets, events, and profiles.

        Args:
            query: Search query string
            limit: Max number of results

        Returns:
            List of search results
        """
        url = self._build_url("/public-search")
        params = {"query": query, "limit": limit}
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Tags API
    # ====================

    async def list_tags(
        self, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        List all tags.

        Args:
            limit: Max number of tags to return
            offset: Pagination offset

        Returns:
            List of tag objects
        """
        url = self._build_url("/tags")
        params = {"limit": limit, "offset": offset}
        return await self._request_with_retry("GET", url, params=params)

    async def get_tag_by_id(self, tag_id: str) -> Optional[dict[str, Any]]:
        """
        Get a specific tag by ID.

        Args:
            tag_id: The tag ID

        Returns:
            Tag object or None if not found
        """
        url = self._build_url(f"/tags/{tag_id}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_tag_by_slug(self, slug: str) -> Optional[dict[str, Any]]:
        """
        Get a specific tag by slug.

        Args:
            slug: The tag slug

        Returns:
            Tag object or None if not found
        """
        url = self._build_url(f"/tags/slug/{slug}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_related_tags(self, tag_id: str) -> list[dict[str, Any]]:
        """
        Get tags related to a specific tag.

        Args:
            tag_id: The tag ID

        Returns:
            List of related tag objects
        """
        url = self._build_url(f"/tags/{tag_id}/related-tags/tags")
        return await self._request_with_retry("GET", url)

    async def get_tag_relationships(
        self, tag_id: str
    ) -> list[dict[str, Any]]:
        """
        Get tag relationships (related tag IDs with ranks) for a tag.

        Args:
            tag_id: The tag ID

        Returns:
            List of relationship objects
        """
        url = self._build_url(f"/tags/{tag_id}/related-tags")
        return await self._request_with_retry("GET", url)

    async def get_tag_relationships_by_slug(
        self, slug: str
    ) -> list[dict[str, Any]]:
        """
        Get tag relationships (related tag IDs with ranks) for a tag by slug.

        Args:
            slug: The tag slug

        Returns:
            List of relationship objects
        """
        url = self._build_url(f"/tags/slug/{slug}/related-tags")
        return await self._request_with_retry("GET", url)

    async def get_related_tags_by_slug(self, slug: str) -> list[dict[str, Any]]:
        """
        Get tags related to a specific tag by slug.

        Args:
            slug: The tag slug

        Returns:
            List of related tag objects
        """
        url = self._build_url(f"/tags/slug/{slug}/related-tags/tags")
        return await self._request_with_retry("GET", url)

    # ====================
    # Series API
    # ====================

    async def list_series(
        self, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        List all series.

        Args:
            limit: Max number of series to return
            offset: Pagination offset

        Returns:
            List of series objects
        """
        url = self._build_url("/series")
        params = {"limit": limit, "offset": offset}
        return await self._request_with_retry("GET", url, params=params)

    async def get_series_by_id(self, series_id: str) -> Optional[dict[str, Any]]:
        """
        Get a specific series by ID.

        Args:
            series_id: The series ID

        Returns:
            Series object or None if not found
        """
        url = self._build_url(f"/series/{series_id}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    # ====================
    # Comments API
    # ====================

    async def list_comments(
        self, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        List all comments.

        Args:
            limit: Max number of comments to return
            offset: Pagination offset

        Returns:
            List of comment objects
        """
        url = self._build_url("/comments")
        params = {"limit": limit, "offset": offset}
        return await self._request_with_retry("GET", url, params=params)

    async def get_comments_by_id(
        self, comment_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Get comments by comment ID.

        Args:
            comment_id: The comment ID

        Returns:
            Comment object or None if not found
        """
        url = self._build_url(f"/comments/{comment_id}")
        try:
            return await self._request_with_retry("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_comments_by_user(
        self, user_address: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get comments by user address.

        Args:
            user_address: The user's wallet address
            limit: Max number of comments to return

        Returns:
            List of comment objects
        """
        url = self._build_url(f"/comments/user_address/{user_address.lower()}")
        params = {"limit": limit}
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Profile API
    # ====================

    async def get_public_profile(
        self, address: str
    ) -> Optional[dict[str, Any]]:
        """
        Get public profile by wallet address.

        Args:
            address: The wallet address

        Returns:
            Profile object or None if not found
        """
        url = self._build_url("/public-profile")
        params = {"address": address.lower()}
        try:
            result = await self._request_with_retry("GET", url, params=params)
            if isinstance(result, dict) and result.get("error") == "profile not found":
                return None
            return result
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    # ====================
    # Sports API
    # ====================

    async def get_sports_metadata(self) -> dict[str, Any]:
        """
        Get sports metadata information.

        Returns:
            Sports metadata object
        """
        url = self._build_url("/sports")
        return await self._request_with_retry("GET", url)

    async def get_sports_market_types(self) -> list[str]:
        """
        Get valid sports market types.

        Returns:
            List of market type strings
        """
        url = self._build_url("/sports/market-types")
        return await self._request_with_retry("GET", url)

    async def list_teams(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        List all teams.

        Args:
            limit: Max number of teams to return

        Returns:
            List of team objects
        """
        url = self._build_url("/teams")
        params = {"limit": limit}
        return await self._request_with_retry("GET", url, params=params)

    # ====================
    # Market Makers / Builders API
    # ====================

    async def get_builder_leaderboard(
        self, limit: int = 100, time_period: str = "30d"
    ) -> list[dict[str, Any]]:
        """
        Get aggregated builder leaderboard.

        Args:
            limit: Max number of entries
            time_period: Time period (24h, 7d, 30d, allTime)

        Returns:
            List of builder leaderboard entries
        """
        url = self._build_url("/v1/builders/leaderboard")
        params = {"limit": limit, "timePeriod": time_period}
        return await self._request_with_retry("GET", url, params=params)

    async def get_builder_volume(
        self, time_period: str = "30d"
    ) -> list[dict[str, Any]]:
        """
        Get daily builder volume time-series.

        Args:
            time_period: Time period (24h, 7d, 30d, allTime)

        Returns:
            List of volume data points
        """
        url = self._build_url("/v1/builders/volume")
        params = {"timePeriod": time_period}
        return await self._request_with_retry("GET", url, params=params)


# Singleton instance
_gamma_client: Optional[GammaClient] = None


def get_gamma_client() -> GammaClient:
    """Get the singleton Gamma client instance."""
    global _gamma_client
    if _gamma_client is None:
        _gamma_client = GammaClient()
    return _gamma_client


async def close_gamma_client() -> None:
    """Close the Gamma client connection."""
    global _gamma_client
    if _gamma_client is not None:
        await _gamma_client.close()
        _gamma_client = None
