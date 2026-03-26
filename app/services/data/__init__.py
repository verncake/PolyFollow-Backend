"""Data API client module."""
from app.services.data.client import (
    DataClient,
    get_data_client,
    close_data_client,
)

__all__ = ["DataClient", "get_data_client", "close_data_client"]
