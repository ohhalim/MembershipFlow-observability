from unittest.mock import Mock

from fastapi.testclient import TestClient

import app.main as main_module


def test_liveness_does_not_query_database() -> None:
    application = main_module.create_app()
    application.state.database_engine = Mock()

    response = TestClient(application).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
    application.state.database_engine.assert_not_called()


def test_readiness_returns_503_without_database(monkeypatch) -> None:
    application = main_module.create_app()

    def fail_readiness(*_args) -> None:
        raise RuntimeError("database migration revision mismatch")

    monkeypatch.setattr(main_module, "verify_database_ready", fail_readiness)

    response = TestClient(application).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database not ready"}


def test_readiness_returns_up_for_expected_revision(monkeypatch) -> None:
    application = main_module.create_app()
    monkeypatch.setattr(main_module, "verify_database_ready", lambda *_args: None)

    response = TestClient(application).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
