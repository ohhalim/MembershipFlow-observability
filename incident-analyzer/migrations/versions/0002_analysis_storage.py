"""Create evidence bundle and analysis result storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002_analysis_storage"
down_revision = "0001_incident_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_bundles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.String(length=26), nullable=False),
        sa.Column("analysis_revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("collector_version", sa.String(length=32), nullable=False),
        sa.Column("window_start", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("window_end", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("content_json", mysql.JSON(), nullable=False),
        sa.Column("content_sha256", mysql.BINARY(length=32), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "incident_id", "analysis_revision", name="uq_evidence_bundle_revision"
        ),
    )
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.String(length=26), nullable=False),
        sa.Column("analysis_revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("content_json", mysql.JSON(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "incident_id", "analysis_revision", name="uq_analysis_result_revision"
        ),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("evidence_bundles")
