from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BINARY, DATETIME, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IncidentModel(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("dedup_key", "started_at", name="uq_incident_episode"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    external_fingerprint: Mapped[str | None] = mapped_column(String(255))
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    episode_status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    payload_version: Mapped[str] = mapped_column(String(16), nullable=False)
    masked_event_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    jobs: Mapped[list["AnalysisJobModel"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class AnalysisJobModel(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "analysis_revision", name="uq_analysis_job_revision"
        ),
        Index(
            "ix_analysis_jobs_claim",
            "status",
            "available_at",
            "lease_until",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("incidents.id"), nullable=False
    )
    analysis_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    incident: Mapped[IncidentModel] = relationship(back_populates="jobs")


class EvidenceBundleModel(Base):
    __tablename__ = "evidence_bundles"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "analysis_revision", name="uq_evidence_bundle_revision"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("incidents.id"), nullable=False
    )
    analysis_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    collector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[bytes] = mapped_column(BINARY(32), nullable=False)


class AnalysisResultModel(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "analysis_revision", name="uq_analysis_result_revision"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("incidents.id"), nullable=False
    )
    analysis_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class NotificationDeliveryModel(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "analysis_revision",
            "destination",
            name="uq_notification_delivery_destination",
        ),
        Index(
            "ix_notification_deliveries_claim",
            "status",
            "available_at",
            "lease_until",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("incidents.id"), nullable=False
    )
    analysis_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    destination: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
