import os

import pytest

os.environ.setdefault("INCIDENT_DB_PASSWORD", "unit_test_runtime_password")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "anyio: asyncio test")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
