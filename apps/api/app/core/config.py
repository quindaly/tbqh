"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+psycopg://app:app@db:5432/app"

    # URLs
    API_BASE_URL: str = "http://localhost:8000"
    WEB_BASE_URL: str = "http://localhost:3000"

    # LLM
    LLM_PROVIDER: str = "openai_compatible"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4.1-mini"
    LLM_BASE_URL: str | None = None

    # Embeddings
    EMBEDDINGS_MODEL: str = "text-embedding-3-small"
    EMBEDDINGS_DIMENSION: int = 1536

    # Email
    EMAIL_PROVIDER: str = "console"
    EMAIL_FROM: str = "no-reply@example.com"

    # Security
    COOKIE_SECRET: str = "dev-secret-change-me"
    MAGIC_LINK_MAX_AGE: int = 600  # 10 minutes
    SESSION_COOKIE_NAME: str = "session"

    # SSL verification (set to false for corporate proxies doing SSL inspection)
    SSL_VERIFY: bool = False

    # Recommendation defaults
    DEFAULT_BATCH_SIZE: int = 10
    DEFAULT_CANDIDATE_K: int = 200
    DEFAULT_TOP_SIMILARITY_N: int = 7
    DEFAULT_EXPLORE_N: int = 3
    DEFAULT_EXPLORE_POLICY: str = "diverse"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
