from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str
    # The owner that runs the migrations. Empty: the migrations run as DATABASE_URL. When it names another role
    # than DATABASE_URL, the migrations create that application role and grant it limited rights (app/db_role.py).
    migration_database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO. S3_ENDPOINT is a URL such as http://minio:9000.
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_evidence: str = "evidence"
    # COMPLIANCE: nobody, the MinIO root key included, can delete or shorten the lock before it ends. GOVERNANCE
    # can be bypassed by a key with that right and is meant for development only (.env.example).
    evidence_lock_mode: Literal["GOVERNANCE", "COMPLIANCE"] = "COMPLIANCE"
    evidence_retention_days: int = Field(default=1825, ge=1)
    tsa_url: str = ""

    # No default on purpose: the service must not start with a guessable secret.
    jwt_secret: str = Field(min_length=32)
    jwt_ttl_minutes: int = Field(default=480, ge=1)
    # Failed logins allowed per account and per client IP within the window, then the login waits for its end.
    login_max_failures_per_user: int = Field(default=5, ge=1)
    login_max_failures_per_ip: int = Field(default=20, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)

    llm_enabled: bool = False
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3.5:9b-q6k"
    llm_timeout_s: int = 120

    # Help assistant for officers (docs/ASSISTANT.md): any OpenAI-compatible `/chat/completions`. Off by default;
    # while off there are no /api/v1/assistant routes at all (404).
    assistant_enabled: bool = False
    assistant_base_url: str = "http://host.docker.internal:11434/v1"
    assistant_api_key: str = ""
    assistant_model: str = "qwen3.5:9b-q6k"
    # Empty: the field is not sent (providers that do not know it).
    assistant_reasoning_effort: str = "none"
    assistant_timeout_s: int = Field(default=120, ge=1)
    assistant_max_tool_rounds: int = Field(default=4, ge=1, le=10)

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

    # Telegram userbot (SPEC 10.8): a user account that reads public channels and groups through MTProto. Both values
    # come from https://my.telegram.org; with an empty one the userbot is off. An empty TELEGRAM_API_ID in .env is 0.
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    userbot_session: str = "/data/userbot/saq"
    userbot_join_delay_s: float = Field(default=60, ge=0)
    userbot_backfill_limit: int = Field(default=100, ge=1)

    # Text recognition on photos of publications (SPEC 10.2); runs locally, nothing leaves the server.
    ocr_enabled: bool = True
    ocr_languages: str = "rus+kaz+eng"

    # SAQ VISION (docs/SAQ_VISION_ARCHITECTURE.md): off by default; when off, no /api/v1/vision routes exist.
    vision_enabled: bool = False
    s3_bucket_vision: str = "vision"
    vision_max_photo_mb: int = Field(default=25, ge=1)
    vision_max_video_mb: int = Field(default=1024, ge=1)
    vision_max_duration_seconds: int = Field(default=1800, ge=1)
    vision_frame_interval_seconds: float = Field(default=3, gt=0)
    vision_max_frames: int = Field(default=400, ge=1)
    # "grounding_dino" runs the open-vocabulary detector (experimental, pretrained, not fine-tuned) in `vision-worker`.
    vision_detector_backend: Literal["disabled", "grounding_dino"] = "disabled"
    vision_detector_model: str = "IDEA-Research/grounding-dino-tiny"
    vision_detector_box_threshold: float = Field(default=0.35, ge=0, le=1)
    vision_detector_text_threshold: float = Field(default=0.25, ge=0, le=1)
    # The detector gets a copy of the frame with its longer side at most this many pixels.
    vision_detector_max_side: int = Field(default=800, ge=64)
    vision_detector_device: Literal["auto", "cpu", "cuda"] = "auto"
    # Frames per forward pass; 0 picks 2 on CPU and 8 on a GPU.
    vision_detector_batch_size: int = Field(default=0, ge=0, le=64)

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

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def _empty_api_id_is_unset(cls, value: object) -> object:
        return 0 if isinstance(value, str) and not value.strip() else value

    @property
    def migration_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def userbot_configured(self) -> bool:
        """The userbot serves Telegram when it has its credentials and the Telegram source is switched on."""
        return self.collect_telegram_enabled and self.telegram_api_id > 0 and bool(self.telegram_api_hash.strip())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
