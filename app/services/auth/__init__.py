"""
Authentication module for Polymarket API.

Provides:
- Wallet authentication (EIP-712 signing)
- API Key authentication
- Authenticated API clients (Trade, Rewards, Rebates, Bridge, Relayer)
"""
from app.services.auth.wallet import (
    WalletAuthenticator,
    WalletCredentials,
    get_wallet_authenticator,
    configure_wallet_authenticator,
)
from app.services.auth.base import AuthenticatedClient
from app.services.auth.trade_client import (
    TradeClient,
    get_trade_client,
    close_trade_client,
)
from app.services.auth.rewards_client import (
    RewardsClient,
    get_rewards_client,
    close_rewards_client,
)
from app.services.auth.rebates_client import (
    RebatesClient,
    get_rebates_client,
    close_rebates_client,
)
from app.services.auth.bridge_client import (
    BridgeClient,
    get_bridge_client,
    close_bridge_client,
)
from app.services.auth.relayer_client import (
    RelayerClient,
    get_relayer_client,
    close_relayer_client,
)

__all__ = [
    # Wallet Auth
    "WalletAuthenticator",
    "WalletCredentials",
    "get_wallet_authenticator",
    "configure_wallet_authenticator",
    # Authenticated Clients
    "AuthenticatedClient",
    # Trade
    "TradeClient",
    "get_trade_client",
    "close_trade_client",
    # Rewards
    "RewardsClient",
    "get_rewards_client",
    "close_rewards_client",
    # Rebates
    "RebatesClient",
    "get_rebates_client",
    "close_rebates_client",
    # Bridge
    "BridgeClient",
    "get_bridge_client",
    "close_bridge_client",
    # Relayer
    "RelayerClient",
    "get_relayer_client",
    "close_relayer_client",
]
