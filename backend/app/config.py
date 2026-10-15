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

    # The scheduled sync of the housing portal registry stays off until АО «КЖК» agrees to it (OPEN_QUESTIONS 11).
    # An administrator can still start a run by hand.
    homeportal_sync_enabled: bool = False

    # Automatic collection of publications (SPEC 10.1). Every collector is off until enabled: real sources are
    # collected only by a deployment that chose to (OPEN_QUESTIONS 30).
    collect_telegram_enabled: bool = False
    collect_olx_enabled: bool = False
    collect_krisha_enabled: bool = False
    # Instagram is read only through the official Graph API (Business Discovery); an empty token keeps it off.
    instagram_graph_token: str = ""
    instagram_graph_user_id: str = ""
    instagram_graph_api_version: str = "v26.0"
    collect_request_delay_s: float = Field(default=2.0, ge=0)
    collect_max_pages: int = Field(default=3, ge=1)
    collect_user_agent: str = "Mozilla/5.0 (compatible; SAQ-Qurylys/1.0; public advertising monitoring)"

    # Text recognition on photos of publications (SPEC 10.2); runs locally, nothing leaves the server.
    ocr_enabled: bool = True
    ocr_languages: str = "rus+kaz+eng"

    # Telegram bot for citizens (SPEC 10.4); an empty token keeps it off.
    telegram_bot_token: str = ""
    bot_reports_per_hour: int = Field(default=10, ge=1)

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
