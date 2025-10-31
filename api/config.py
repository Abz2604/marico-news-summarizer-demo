from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "api/.env", "api/.env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Marico News Summarizer API")
    env: str = Field(default="development")
    debug: bool = Field(default=False)

    # Authentication / security
    jwt_secret_key: str = Field(default="dev-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_exp_minutes: int = Field(default=60)

    # Snowflake connection parameters
    snowflake_account: Optional[str] = None
    snowflake_user: Optional[str] = None
    snowflake_password: Optional[str] = None
    snowflake_role: Optional[str] = None
    snowflake_warehouse: Optional[str] = None
    snowflake_database: Optional[str] = None
    snowflake_schema: Optional[str] = None

    # OpenAI / LLM settings
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4.1")

    # Agent execution guard rails
    agent_max_articles: int = Field(default=5)
    agent_request_timeout_seconds: int = Field(default=60)
    agent_hard_timeout_seconds: int = Field(default=90)

    # Network / Proxy
    proxy_url: Optional[str] = Field(default=None, alias="PROXY_URL")

    # Bing Web Search API
    bing_search_api_key: Optional[str] = Field(default=None, alias="BING_SEARCH_API_KEY")
    bing_search_endpoint: str = Field(default="https://api.bing.microsoft.com/v7.0/search")

    # No inner Config; using model_config above


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
