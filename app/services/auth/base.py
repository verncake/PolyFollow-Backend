"""
Base client for authenticated Polymarket APIs.

Provides API Key and wallet-based authentication.
"""
import httpx
from typing import Optional, Any, Dict
import asyncio
import os

from app.services.base import BasePolymarketClient, PolymarketAPIError
from app.services.auth.wallet import get_wallet_authenticator


class AuthenticatedClient(BasePolymarketClient):
    """
    Base client for authenticated API calls.

    Supports:
    - API Key authentication (X-API-Key header)
    - Wallet signature authentication
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        super().__init__(base_url)
        self.api_key = api_key or os.getenv("POLYMARKET_API_KEY")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _auth_request(
        self,
        method: str,
        url: str,
        wallet_sig: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Make authenticated request.

        Args:
            method: HTTP method
            url: Full URL
            wallet_sig: Optional wallet signature
            **kwargs: Additional request arguments

        Returns:
            Response JSON
        """
        headers = self._get_auth_headers()

        if wallet_sig:
            headers["X-Wallet-Signature"] = wallet_sig

        kwargs["headers"] = headers
        return await self._request_with_retry(method, url, **kwargs)

    async def _get(
        self, url: str, wallet_sig: Optional[str] = None, **kwargs
    ) -> Any:
        """Authenticated GET request."""
        return await self._auth_request("GET", url, wallet_sig, **kwargs)

    async def _post(
        self,
        url: str,
        wallet_sig: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Authenticated POST request."""
        return await self._auth_request("POST", url, wallet_sig, **kwargs)

    async def _delete(
        self, url: str, wallet_sig: Optional[str] = None, **kwargs
    ) -> Any:
        """Authenticated DELETE request."""
        return await self._auth_request("DELETE", url, wallet_sig, **kwargs)
