from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO. S3_ENDPOINT is a URL such as http://minio:9000.
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_evidence: str = "evidence"
    evidence_lock_mode: Literal["GOVERNANCE", "COMPLIANCE"] = "GOVERNANCE"
    evidence_retention_days: int = Field(default=1, ge=1)
    tsa_url: str = ""

    # No default on purpose: the service must not start with a guessable secret.
    jwt_secret: str = Field(min_length=32)
    jwt_ttl_minutes: int = Field(default=480, ge=1)

    llm_enabled: bool = False
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3.5:9b-q6k"
    llm_timeout_s: int = 120

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    cors_origins: str = "http://localhost:8080,http://localhost:5173"

    initial_admin_username: str = "admin"
    initial_admin_password: str = ""
    demo_user_password: str = ""

    max_upload_mb: int = Field(default=25, ge=1)

    # Turn off in tests: object_changed() then does not touch the Celery broker.
    events_enabled: bool = True

    @field_validator("s3_endpoint")
    @classmethod
    def _endpoint_has_scheme(cls, value: str) -> str:
        if urlparse(value).scheme not in {"http", "https"}:
            raise ValueError("S3_ENDPOINT must be a URL like http://minio:9000")
        return value.rstrip("/")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
