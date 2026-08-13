"""Create incident and analysis job storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001_incident_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("external_fingerprint", sa.String(length=255), nullable=True),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("episode_status", sa.String(length=32), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("resolved_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("payload_version", sa.String(length=16), nullable=False),
        sa.Column("masked_event_json", mysql.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_incidents_dedup_started",
        "incidents",
        ["dedup_key", "started_at"],
        unique=False,
    )
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.String(length=26), nullable=False),
        sa.Column("analysis_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("available_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "incident_id",
            "analysis_revision",
            name="uq_analysis_job_revision",
        ),
    )
    op.create_index(
        "ix_analysis_jobs_claim",
        "analysis_jobs",
        ["status", "available_at", "lease_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_claim", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_incidents_dedup_started", table_name="incidents")
    op.drop_table("incidents")
