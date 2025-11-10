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
    use_snowflake: bool = Field(default=False)  # Feature flag to enable/disable Snowflake
    snowflake_account: Optional[str] = None
    snowflake_user: Optional[str] = None
    snowflake_password: Optional[str] = None
    snowflake_role: Optional[str] = None
    snowflake_warehouse: Optional[str] = None
    snowflake_database: Optional[str] = None
    snowflake_schema: Optional[str] = None

    # Azure OpenAI settings (PRIMARY - client provided)
    azure_openai_key: Optional[str] = Field(default=None, alias="AZURE_OPENAI_KEY")
    azure_openai_endpoint: str = Field(default="https://milazdalle.openai.azure.com/")
    azure_openai_api_version: str = Field(default="2024-12-01-preview")
    # Azure deployments
    azure_deployment_gpt4o: str = Field(default="gpt-4o")  # For complex reasoning
    azure_deployment_gpt4o_mini: str = Field(default="gpt-4o-mini")  # For simple tasks
    
    # Legacy OpenAI settings (kept for backward compatibility, not used)
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4o")  # Updated default to match Azure
    # Optional per-task overrides (fallback to openai_model if unset)
    intent_extractor_model: Optional[str] = None
    context_extractor_model: Optional[str] = None
    page_analyzer_model: Optional[str] = None
    link_extractor_model: Optional[str] = None
    date_parser_model: Optional[str] = None
    content_validator_model: Optional[str] = None

    # Agent execution guard rails
    agent_max_articles: int = Field(default=5)
    agent_request_timeout_seconds: int = Field(default=60)
    agent_hard_timeout_seconds: int = Field(default=90)
    # Deduplication controls
    enable_semantic_dedup: bool = Field(default=False)
    dedup_min_articles: int = Field(default=8)

    # Network / Proxy
    proxy_url: Optional[str] = Field(default=None, alias="PROXY_URL")

    # BrightData Scraping API
    brightdata_api_key: Optional[str] = Field(default=None, alias="BRIGHTDATA_API_KEY")
    brightdata_zone: str = Field(default="web_unlocker1_marico", alias="BRIGHTDATA_ZONE")
    
    # News API (if used)
    newsapi_key: Optional[str] = Field(default=None, alias="NEWSAPI_KEY")

    # Bing Web Search API
    bing_search_api_key: Optional[str] = Field(default=None, alias="BING_SEARCH_API_KEY")
    bing_search_endpoint: str = Field(default="https://api.bing.microsoft.com/v7.0/search")

    # SMTP Settings from implementation-particulars.md
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_sender_email: str = "ds-support@marico.com"
    smtp_password: Optional[str] = Field(default=None, alias="EMAIL_PASSWORD")

    # No inner Config; using model_config above


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
