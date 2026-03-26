"""
TradeTask Pydantic models for Follow-Alpha protocol.
JSON serializable for cross-language support (Python/Go).
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
import uuid
from datetime import datetime, timezone


class TradeTask(BaseModel):
    """跟单任务协议 - JSON 序列化，支持跨语言 (Python/Go)"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "user_123",
                "target_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f",
                "market_id": "abc123_condition_id",
                "outcome": "Yes",
                "amount_usdc": "10.5",
                "price_limit": None,
                "created_at": "2026-03-26T10:00:00Z",
            }
        }
    )

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    target_address: str
    market_id: str
    outcome: str = Field(pattern="^(Yes|No)$")
    amount_usdc: str
    price_limit: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
