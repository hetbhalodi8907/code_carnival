from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Secure Multi-Modal RAG System"
    app_env: str = "development"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    max_pdf_size_mb: int = 25
    # Image (OCR) uploads.
    max_image_size_mb: int = Field(default=10, ge=1)
    max_image_pixels: int = Field(default=25_000_000, ge=1)
    ocr_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    chunk_size: int = 4000
    chunk_overlap: int = 200
    document_storage_path: str = "data/documents"

    # Local embeddings by default: no API key, and no network after the first model download.
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=1)
    embedding_batch_size: int = Field(default=100, ge=1)
    # Only for EMBEDDING_PROVIDER=openai.
    openai_api_key: str | None = None

    # Answer-generation LLM (OpenAI-compatible chat API). Groq has no embeddings API,
    # so embeddings stay on EMBEDDING_PROVIDER. "lm_studio" makes the local model the only
    # provider: no Groq key is needed and nothing is sent to a cloud API.
    llm_provider: Literal["groq", "lm_studio"] = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: SecretStr | None = None
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    llm_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    # A rate-limited call waits once for the provider's Retry-After if it is at most this long.
    llm_rate_limit_max_wait_seconds: float = Field(default=45.0, ge=0.0, le=120.0)

    # Local model (LM Studio-compatible OpenAI server on this machine). Used as the only provider
    # when LLM_PROVIDER=lm_studio, or as an optional fallback behind Groq when LM_STUDIO_ENABLED
    # is true (tried at most once, only after a rate limit, timeout or unavailability).
    # The model ID must be the exact one the running server reports at /v1/models.
    lm_studio_enabled: bool = False
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_model: str = ""
    # Only needed if the LM Studio server has authentication enabled.
    lm_studio_api_key: SecretStr | None = None
    lm_studio_timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    lm_studio_max_output_tokens: int = Field(default=2048, ge=1, le=8192)

    # RAG context budget: total characters of retrieved chunk text per context. Whole
    # lower-ranked items beyond it are left out (and counted), never cut mid-item.
    rag_max_context_characters: int = Field(default=32_000, ge=1_000)

    # "Access denied" signal (see app/services/rag/access_denial.py). Only consulted after the
    # assistant could not answer from the user's authorized context. A document-relevance probe
    # over documents the user may NOT read reports denial only when its best similarity reaches
    # the minimum AND beats the best authorized similarity by the margin; otherwise the answer
    # stays "insufficient information". Calibrated on the synthetic demo documents with the default
    # local model (all-MiniLM-L6-v2): restricted-topic questions scored 0.39-0.57 and led by
    # 0.14+, unanswerable questions never led by more than 0.09. Recalibrate for another model.
    access_denial_min_similarity: float = Field(default=0.40, ge=0.0, le=1.0)
    access_denial_margin: float = Field(default=0.10, ge=0.0, le=1.0)

    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)

    database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: float = 30.0
    db_echo: bool = False

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> "Settings":
        """Refuse weak JWT secrets anywhere, and a missing one in production."""
        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if secret and len(secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters.")
        if self.app_env.lower() == "production" and not secret:
            raise ValueError("JWT_SECRET_KEY is required when APP_ENV is production.")
        return self

    @model_validator(mode="after")
    def validate_local_fallback(self) -> "Settings":
        """A local provider or fallback needs a model, and must stay on this machine.

        Authorized document context is sent to the fallback, so a non-loopback host is refused
        rather than silently sending that content to another machine.
        """
        if not (self.lm_studio_enabled or self.llm_provider == "lm_studio"):
            return self
        if not self.lm_studio_model.strip():
            raise ValueError("LM_STUDIO_MODEL is required when LLM_PROVIDER=lm_studio or LM_STUDIO_ENABLED is true.")
        host = urlparse(self.lm_studio_base_url).hostname or ""
        try:
            loopback = host == "localhost" or ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError("LM_STUDIO_BASE_URL must point at this machine (localhost, 127.0.0.1 or ::1).")
        return self


settings = Settings()
