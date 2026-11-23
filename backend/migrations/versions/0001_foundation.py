"""Create the personal workspace and source intake schema."""
from datetime import UTC, datetime
from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def record_columns():
    return (
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade():
    workspace = op.create_table(
        "workspaces", *record_columns(), sa.Column("name", sa.String(120), nullable=False)
    )
    timestamp = datetime.now(UTC)
    op.bulk_insert(workspace, [{
        "id": UUID("3f4cb678-5474-4fa0-98e0-aab0cf8a2e0e"),
        "name": "Personal workspace", "created_at": timestamp, "updated_at": timestamp,
    }])
    op.create_table(
        "projects", *record_columns(),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("workflow", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.CheckConstraint("workflow in ('video','script')", name="project_workflow"),
        sa.CheckConstraint("status in ('draft','ready')", name="project_status"),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    op.create_table(
        "sources", *record_columns(),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("kind in ('video','script')", name="source_kind"),
    )
    op.create_index("ix_sources_project_id", "sources", ["project_id"])
    op.create_table(
        "processing_jobs", *record_columns(),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processing_jobs_project_id", "processing_jobs", ["project_id"])


def downgrade():
    op.drop_table("processing_jobs")
    op.drop_table("sources")
    op.drop_table("projects")
    op.drop_table("workspaces")
