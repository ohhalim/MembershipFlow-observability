import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_restrict_database_and_pool() -> None:
    settings = Settings(
        incident_db_password="runtime_test_password",
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )

    assert settings.incident_db_name == "membershipflow_incident"
    assert settings.db_pool_size + settings.db_max_overflow == 2
    assert "runtime_test_password" not in repr(settings.database_url())


def test_settings_allow_two_minute_llm_analysis() -> None:
    settings = Settings(
        incident_db_password="runtime_test_password",
        _env_file=None,
    )

    assert settings.llm_timeout_seconds == 120
    assert settings.job_lease_seconds > settings.llm_timeout_seconds


def test_settings_reject_llm_timeout_over_two_minutes() -> None:
    with pytest.raises(ValidationError):
        Settings(
            incident_db_password="runtime_test_password",
            llm_timeout_seconds=121,
            _env_file=None,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("incident_db_name", "membershipflow"),
        ("db_pool_size", 3),
        ("db_max_overflow", 1),
    ],
)
def test_settings_reject_shared_database_or_excess_connections(
    field: str, value: str | int
) -> None:
    values = {
        "incident_db_password": "runtime_test_password",
        field: value,
        "_env_file": None,
    }

    with pytest.raises(ValidationError):
        Settings(**values)


def test_settings_rejects_local_webhook_secret_in_production() -> None:
    with pytest.raises(ValidationError, match="production webhook secret"):
        Settings(
            incident_db_password="runtime_test_password",
            app_environment="production",
            incident_webhook_secret="local_webhook_secret_change_before_production",
            _env_file=None,
        )
