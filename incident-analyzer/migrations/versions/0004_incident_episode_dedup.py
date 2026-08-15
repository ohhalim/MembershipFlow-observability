"""Deduplicate incident episodes and enforce one incident per alert episode."""

import sqlalchemy as sa
from alembic import op

revision = "0004_incident_episode_dedup"
down_revision = "0003_slack_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "notification_deliveries",
        "analysis_results",
        "evidence_bundles",
        "analysis_jobs",
    ):
        op.execute(
            sa.text(
                f"DELETE child FROM {table} AS child "
                "JOIN incidents AS duplicate ON duplicate.id = child.incident_id "
                "JOIN incidents AS keeper "
                "ON keeper.dedup_key = duplicate.dedup_key "
                "AND keeper.started_at = duplicate.started_at "
                "AND keeper.id < duplicate.id"
            )
        )
    op.execute(
        sa.text(
            "DELETE duplicate FROM incidents AS duplicate "
            "JOIN incidents AS keeper "
            "ON keeper.dedup_key = duplicate.dedup_key "
            "AND keeper.started_at = duplicate.started_at "
            "AND keeper.id < duplicate.id"
        )
    )
    op.drop_index("ix_incidents_dedup_started", table_name="incidents")
    op.create_unique_constraint(
        "uq_incident_episode", "incidents", ["dedup_key", "started_at"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_incident_episode", "incidents", type_="unique")
    op.create_index(
        "ix_incidents_dedup_started",
        "incidents",
        ["dedup_key", "started_at"],
        unique=False,
    )
