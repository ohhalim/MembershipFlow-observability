from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    incident_db_host: str = "mysql"
    app_environment: str = "local"
    incident_db_port: int = Field(default=3306, ge=1, le=65535)
    incident_db_name: str = "membershipflow_incident"
    incident_db_username: str = "incident_analyzer_runtime"
    incident_db_password: SecretStr
    db_pool_size: int = Field(default=2, ge=1, le=2)
    db_max_overflow: int = Field(default=0, ge=0, le=0)
    db_pool_timeout_seconds: int = Field(default=2, ge=1, le=5)
    expected_db_revision: str = "0004_incident_episode_dedup"
    incident_webhook_secret: SecretStr = SecretStr(
        "local_webhook_secret_change_before_production"
    )
    incident_webhook_tolerance_seconds: int = Field(default=300, ge=30, le=600)
    incident_payload_max_bytes: int = Field(default=65_536, ge=1024, le=65_536)
    loki_base_url: str = "http://loki:3100"
    loki_query_timeout_seconds: float = Field(default=5.0, ge=1.0, le=5.0)
    loki_query_limit: int = Field(default=200, ge=1, le=200)
    gemini_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=20.0, ge=1.0, le=20.0)
    llm_max_output_tokens: int = Field(default=4096, ge=128, le=4096)
    slack_webhook_url: SecretStr | None = None
    slack_timeout_seconds: float = Field(default=5.0, ge=1.0, le=10.0)
    notification_lease_seconds: int = Field(default=30, ge=10, le=120)
    notification_max_attempts: int = Field(default=5, ge=1, le=10)
    job_lease_seconds: int = Field(default=120, ge=30, le=300)
    job_max_attempts: int = Field(default=3, ge=1, le=5)

    @field_validator("incident_db_name")
    @classmethod
    def require_incident_database(cls, value: str) -> str:
        if value != "membershipflow_incident":
            raise ValueError("incident analyzer must use membershipflow_incident")
        return value

    @field_validator("loki_base_url")
    @classmethod
    def require_internal_loki_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("loki_base_url must be an HTTP URL")
        return normalized

    @model_validator(mode="after")
    def reject_local_secret_in_production(self) -> "Settings":
        if (
            self.app_environment == "production"
            and self.incident_webhook_secret.get_secret_value()
            == "local_webhook_secret_change_before_production"
        ):
            raise ValueError("production webhook secret must be configured")
        return self

    def database_url(self) -> URL:
        return URL.create(
            drivername="mysql+pymysql",
            username=self.incident_db_username,
            password=self.incident_db_password.get_secret_value(),
            host=self.incident_db_host,
            port=self.incident_db_port,
            database=self.incident_db_name,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
