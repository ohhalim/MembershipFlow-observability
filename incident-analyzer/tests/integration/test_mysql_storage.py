import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, event, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.community.mysql import MySqlContainer

import app.worker as worker_module
from app.config import Settings
from app.domain.analysis import AnalysisResult
from app.domain.evidence import EvidenceBundle, LogEvidence
from app.domain.incident import CreateIncidentCommand
from app.llm import LlmAnalysis
from app.persistence.models import (
    AnalysisJobModel,
    AnalysisResultModel,
    EvidenceBundleModel,
    IncidentModel,
    NotificationDeliveryModel,
)
from app.persistence.repositories import (
    AnalysisJobRepository,
    IncidentRepository,
)

ROOT_PASSWORD = "root_test_password_2026"
RUNTIME_PASSWORD = "runtime_test_password_2026"
MIGRATION_PASSWORD = "migration_test_password_2026"


@pytest.fixture(scope="module")
def mysql_database() -> Iterator[dict[str, str | int]]:
    with MySqlContainer(
        image="mysql:8.0",
        dialect="pymysql",
        username="root",
        password=ROOT_PASSWORD,
        dbname="membershipflow",
    ) as mysql:
        host = mysql.get_container_host_ip()
        port = int(mysql.get_exposed_port(3306))
        root_engine = create_engine(mysql.get_connection_url())
        with root_engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE DATABASE membershipflow_incident "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            connection.execute(
                text(
                    "CREATE USER 'incident_analyzer_runtime'@'%' "
                    f"IDENTIFIED BY '{RUNTIME_PASSWORD}'"
                )
            )
            connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON membershipflow_incident.* "
                    "TO 'incident_analyzer_runtime'@'%'"
                )
            )
            connection.execute(
                text(
                    "CREATE USER 'incident_analyzer_migrator'@'%' "
                    f"IDENTIFIED BY '{MIGRATION_PASSWORD}'"
                )
            )
            connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, "
                    "INDEX, REFERENCES ON membershipflow_incident.* "
                    "TO 'incident_analyzer_migrator'@'%'"
                )
            )
        root_engine.dispose()

        previous = {
            key: os.environ.get(key)
            for key in (
                "INCIDENT_DB_HOST",
                "INCIDENT_DB_PORT",
                "INCIDENT_DB_NAME",
                "INCIDENT_DB_MIGRATION_USERNAME",
                "INCIDENT_DB_MIGRATION_PASSWORD",
            )
        }
        os.environ.update(
            {
                "INCIDENT_DB_HOST": host,
                "INCIDENT_DB_PORT": str(port),
                "INCIDENT_DB_NAME": "membershipflow_incident",
                "INCIDENT_DB_MIGRATION_USERNAME": "incident_analyzer_migrator",
                "INCIDENT_DB_MIGRATION_PASSWORD": MIGRATION_PASSWORD,
            }
        )
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, "head")

        yield {"host": host, "port": port}

        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def runtime_url(database: dict[str, str | int], name: str) -> URL:
    return URL.create(
        "mysql+pymysql",
        username="incident_analyzer_runtime",
        password=RUNTIME_PASSWORD,
        host=str(database["host"]),
        port=int(database["port"]),
        database=name,
        query={"charset": "utf8mb4"},
    )


@pytest.mark.integration
def test_runtime_user_cannot_access_application_database(mysql_database) -> None:
    application_engine = create_engine(runtime_url(mysql_database, "membershipflow"))

    with (
        pytest.raises(OperationalError),
        application_engine.connect() as connection,
    ):
        connection.execute(text("SELECT 1"))

    application_engine.dispose()


@pytest.mark.integration
def test_migration_and_incident_job_transaction(mysql_database) -> None:
    runtime_engine = create_engine(
        runtime_url(mysql_database, "membershipflow_incident")
    )
    session_factory = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    repository = IncidentRepository()
    command_data = CreateIncidentCommand(
        dedup_key="course-api-error-burst",
        started_at=datetime.now(UTC),
        masked_event={"alertname": "ApplicationErrorBurst", "route": "/api/v1/courses"},
    )

    with session_factory() as session:
        created = repository.create_with_job(session, command_data)

    with Session(runtime_engine) as session:
        assert session.scalar(select(func.count()).select_from(IncidentModel)) == 1
        assert session.scalar(select(func.count()).select_from(AnalysisJobModel)) == 1
        job = session.scalar(
            select(AnalysisJobModel).where(
                AnalysisJobModel.incident_id == created.incident_id
            )
        )
        assert job is not None
        assert job.status == "PENDING"
        assert job.analysis_revision == 1

    def fail_job_insert(*_args, **_kwargs) -> None:
        raise RuntimeError("controlled job insert failure")

    event.listen(AnalysisJobModel, "before_insert", fail_job_insert, once=True)
    with (
        session_factory() as session,
        pytest.raises(RuntimeError, match="controlled job insert failure"),
    ):
        repository.create_with_job(
            session,
            CreateIncidentCommand(
                dedup_key="rollback-check",
                started_at=datetime.now(UTC),
                masked_event={"alertname": "RollbackCheck"},
            ),
        )

    with Session(runtime_engine) as session:
        assert session.scalar(select(func.count()).select_from(IncidentModel)) == 1
        assert session.scalar(select(func.count()).select_from(AnalysisJobModel)) == 1

    runtime_engine.dispose()


@pytest.mark.integration
def test_claim_and_complete_analysis_job(mysql_database) -> None:
    runtime_engine = create_engine(
        runtime_url(mysql_database, "membershipflow_incident")
    )
    session_factory = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    repository = AnalysisJobRepository()

    with session_factory() as session:
        claimed = repository.claim_next(session, "integration-worker", 120)
    assert claimed is not None

    now = datetime.now(UTC)
    evidence = EvidenceBundle(
        window_start=now,
        window_end=now,
        log_evidence=[
            LogEvidence(
                evidence_id="L1",
                status="OK",
                signature="request_failed",
                count=2,
                samples=["masked sample"],
            )
        ],
    )
    result = AnalysisResult.model_validate(
        {
            "status": "ANALYZED",
            "facts": [{"statement": "오류 2건 확인", "evidence_ids": ["L1"]}],
            "hypotheses": [
                {
                    "cause": "요청 처리 예외 후보",
                    "evidence_ids": ["L1"],
                    "confidence": "MEDIUM",
                }
            ],
            "excludedCandidates": [],
            "missingEvidence": [],
            "nextChecks": ["메트릭 확인"],
            "rootCauseConfirmed": False,
        }
    )

    with session_factory() as session:
        repository.complete(
            session,
            claimed,
            "integration-worker",
            evidence,
            LlmAnalysis(
                result=result,
                provider="fake",
                model="fake-model",
                input_tokens=100,
                output_tokens=50,
                latency_ms=12,
            ),
        )

    with Session(runtime_engine) as session:
        job = session.get(AnalysisJobModel, claimed.job_id)
        assert job is not None
        assert job.status == "SUCCEEDED"
        assert job.lease_owner is None
        assert (
            session.scalar(select(func.count()).select_from(EvidenceBundleModel)) == 1
        )
        assert (
            session.scalar(select(func.count()).select_from(AnalysisResultModel)) == 1
        )
        delivery = session.scalar(select(NotificationDeliveryModel))
        assert delivery is not None
        assert delivery.status == "PENDING"
        assert delivery.destination == "SLACK"

    runtime_engine.dispose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_notification_delivery_moves_outbox_to_sent(
    mysql_database, monkeypatch
) -> None:
    runtime_engine = create_engine(
        runtime_url(mysql_database, "membershipflow_incident")
    )
    session_factory = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with session_factory() as session:
        pending = session.scalar(
            select(NotificationDeliveryModel).where(
                NotificationDeliveryModel.status == "PENDING"
            )
        )
    assert pending is not None

    class FakeSlackClient:
        async def send(self, payload):
            assert "MembershipFlow 장애 분석" in payload["text"]

    monkeypatch.setattr(worker_module, "SessionFactory", session_factory)
    processed = await worker_module.deliver_notification_once(
        Settings(incident_db_password="test-password", _env_file=None),
        "notification-worker",
        FakeSlackClient(),
    )

    assert processed is True
    with Session(runtime_engine) as session:
        delivery = session.get(NotificationDeliveryModel, pending.id)
        assert delivery is not None
        assert delivery.status == "SENT"
        assert delivery.attempt_count == 1
        assert delivery.lease_owner is None

    runtime_engine.dispose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_worker_moves_pending_job_to_succeeded(
    mysql_database, monkeypatch
) -> None:
    runtime_engine = create_engine(
        runtime_url(mysql_database, "membershipflow_incident")
    )
    session_factory = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with session_factory() as session:
        created = IncidentRepository().create_with_job(
            session,
            CreateIncidentCommand(
                dedup_key="worker-vertical-slice",
                started_at=datetime.now(UTC),
                masked_event={"labels": {"alertname": "ApplicationErrorBurst"}},
            ),
        )

    now = datetime.now(UTC)
    evidence = EvidenceBundle(
        window_start=now,
        window_end=now,
        log_evidence=[
            LogEvidence(
                evidence_id="L1",
                status="OK",
                signature="request_failed",
                count=1,
                samples=["masked sample"],
            )
        ],
    )
    result = AnalysisResult.model_validate(
        {
            "status": "ANALYZED",
            "facts": [{"statement": "오류 1건 확인", "evidence_ids": ["L1"]}],
            "hypotheses": [],
            "excludedCandidates": [],
            "missingEvidence": [],
            "nextChecks": ["메트릭 확인"],
            "rootCauseConfirmed": False,
        }
    )

    class FakeLokiClient:
        async def collect(self, _started_at):
            return evidence

    class FakeLlmClient:
        async def analyze(self, _evidence):
            return LlmAnalysis(
                result=result,
                provider="fake",
                model="fake-model",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            )

    monkeypatch.setattr(worker_module, "SessionFactory", session_factory)
    processed = await worker_module.run_once(
        Settings(incident_db_password="test-password", _env_file=None),
        "vertical-slice-worker",
        FakeLokiClient(),
        FakeLlmClient(),
    )

    assert processed is True
    with Session(runtime_engine) as session:
        job = session.scalar(
            select(AnalysisJobModel).where(
                AnalysisJobModel.incident_id == created.incident_id
            )
        )
        assert job is not None
        assert job.status == "SUCCEEDED"

    runtime_engine.dispose()
