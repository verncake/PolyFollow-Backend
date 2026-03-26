"""
Polymarket API Services.

Modules:
- gamma: Gamma API (Markets, Events, Tags, Series, Comments, Profiles)
- data: Data API (Positions, Trades, Activity, Leaderboard, Holders)
- clob: CLOB API (Order books, Prices, Spreads)
- websocket: WebSocket client (Market, User, Sports channels)
- auth: Authenticated clients (Trade, Rewards, Rebates, Bridge, Relayer)
- account_service: P/L calculation and account metrics
- scoring_service: Trader performance scoring (0-100)
"""
from app.services.gamma import GammaClient, get_gamma_client, close_gamma_client
from app.services.data import DataClient, get_data_client, close_data_client
from app.services.clob import (
    ClobHTTPClient as ClobClient,
    get_clob_client,
    close_clob_client,
    ClobSDKClient,
    get_clob_sdk_client,
    configure_clob_sdk_client,
)
from app.services.websocket import (
    PolymarketWebSocket,
    MarketDataStreamer,
    WebSocketChannel,
)
from app.services.auth import (
    WalletAuthenticator,
    get_wallet_authenticator,
    configure_wallet_authenticator,
    TradeClient,
    get_trade_client,
    close_trade_client,
    RewardsClient,
    get_rewards_client,
    close_rewards_client,
    RebatesClient,
    get_rebates_client,
    close_rebates_client,
    BridgeClient,
    get_bridge_client,
    close_bridge_client,
    RelayerClient,
    get_relayer_client,
    close_relayer_client,
)
from app.services.account_service import (
    calculate_unrealized_pnl,
    calculate_realized_pnl,
    calculate_position_pnl,
    calculate_win_rate,
    calculate_profit_factor,
    calculate_account_summary,
    PositionPnL,
    AccountSummary,
)
from app.services.scoring_service import (
    AddressScorer,
    AddressScores,
    get_scoring_service,
    get_address_scores,
)
from app.services.position_enricher import (
    PositionEnricher,
    EnrichedPosition,
)
from app.services.blockchain import (
    BlockchainClient,
    WalletBalance,
    get_blockchain_client,
)

__all__ = [
    # Gamma API
    "GammaClient",
    "get_gamma_client",
    "close_gamma_client",
    # Data API
    "DataClient",
    "get_data_client",
    "close_data_client",
    # CLOB API (HTTP)
    "ClobClient",
    "get_clob_client",
    "close_clob_client",
    # CLOB API (SDK)
    "ClobSDKClient",
    "get_clob_sdk_client",
    "configure_clob_sdk_client",
    # WebSocket
    "PolymarketWebSocket",
    "MarketDataStreamer",
    "WebSocketChannel",
    # Authenticated Clients
    "WalletAuthenticator",
    "get_wallet_authenticator",
    "configure_wallet_authenticator",
    "TradeClient",
    "get_trade_client",
    "close_trade_client",
    "RewardsClient",
    "get_rewards_client",
    "close_rewards_client",
    "RebatesClient",
    "get_rebates_client",
    "close_rebates_client",
    "BridgeClient",
    "get_bridge_client",
    "close_bridge_client",
    "RelayerClient",
    "get_relayer_client",
    "close_relayer_client",
    # Account Service
    "calculate_unrealized_pnl",
    "calculate_realized_pnl",
    "calculate_position_pnl",
    "calculate_win_rate",
    "calculate_profit_factor",
    "calculate_account_summary",
    "PositionPnL",
    "AccountSummary",
    # Scoring Service
    "AddressScorer",
    "AddressScores",
    "get_scoring_service",
    "get_address_scores",
    # Position Enricher
    "PositionEnricher",
    "EnrichedPosition",
    # Blockchain
    "BlockchainClient",
    "WalletBalance",
    "get_blockchain_client",
]
