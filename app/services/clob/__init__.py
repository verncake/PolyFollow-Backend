"""
CLOB API client module.

Provides:
- ClobClient: HTTP-based client for public market data
- ClobSDKClient: Official SDK-based client for market data and trading
"""
from app.services.clob.client import (
    ClobClient as ClobHTTPClient,
    get_clob_client,
    close_clob_client,
)
from app.services.clob.sdk_client import (
    ClobSDKClient,
    get_clob_sdk_client,
    configure_clob_sdk_client,
)

__all__ = [
    # HTTP Client (public data only)
    "ClobHTTPClient",
    "get_clob_client",
    "close_clob_client",
    # SDK Client (full trading support)
    "ClobSDKClient",
    "get_clob_sdk_client",
    "configure_clob_sdk_client",
]
