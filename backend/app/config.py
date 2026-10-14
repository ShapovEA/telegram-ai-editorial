from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "dev"
    app_secret: str = Field(default="change-me", min_length=8)
    app_public_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    access_token_ttl_minutes: int = 60 * 24 * 7

    database_url: str = "postgresql+psycopg://smm:smm@127.0.0.1:5432/smm"
    redis_url: str = "redis://localhost:6379/0"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_name: str = "AI SMM Department"
    llm_timeout_seconds: float = 180.0
    llm_max_retries: int = 3

    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    searxng_url: str = "http://localhost:8080"
    sandbox_url: str = "http://localhost:8090"
    rsshub_url: str = ""
    pexels_api_key: str = ""

    telegram_bot_token: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    search_cache_ttl_seconds: int = 24 * 3600
    search_min_interval_seconds: float = 1.5

    @property
    def psycopg_dsn(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
