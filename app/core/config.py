"""
Application configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv
import os


def get_env_file_path() -> str:
    """Get absolute path to .env file in backend directory."""
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(backend_root, ".env")


# Load .env file into environment at module import time
load_dotenv(get_env_file_path(), override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_publishable_key: str = ""

    # Supabase Database
    database_url: str = ""
    direct_url: str = ""

    # Upstash Redis
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Polymarket API
    polymarket_clob_api_url: str = "https://clob.polymarket.com"
    polymarket_gamma_api_url: str = "https://gamma-api.polymarket.com"

    # Application
    app_name: str = "Polymarket Follow-Alpha API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    class Config:
        env_file = get_env_file_path()
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
