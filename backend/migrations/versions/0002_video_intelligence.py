"""Add durable video analysis and source-grounded clip review."""
from alembic import op
import sqlalchemy as sa

revision = "0002_video_intelligence"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def record():
    return (
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def source_fk(unique=False):
    return sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, unique=unique)


def upgrade():
    unique = next(c for c in sa.inspect(op.get_bind()).get_unique_constraints("processing_jobs")
                  if c["column_names"] == ["source_id"])
    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("processing_jobs", naming_convention=naming) as batch:
        batch.drop_constraint(unique["name"] or "uq_processing_jobs_source_id", type_="unique")
        batch.alter_column("finished_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch.add_column(sa.Column("stage", sa.String(24), nullable=False, server_default="complete"))
        batch.add_column(sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("progress", sa.Integer(), nullable=False, server_default="100"))
        batch.add_column(sa.Column("error", sa.String(600)))
        batch.add_column(sa.Column("lease_token", sa.Uuid()))
        batch.add_column(sa.Column("lease_until", sa.DateTime(timezone=True)))
    for name, condition in (("uq_job_ingest_source", "kind = 'ingest'"),
                            ("uq_job_active_source", "status in ('queued','running')")):
        predicate = sa.text(condition)
        op.create_index(name, "processing_jobs", ["source_id"], unique=True,
                        postgresql_where=predicate, sqlite_where=predicate)
    op.create_index("ix_job_queue", "processing_jobs", ["status", "created_at"])
    op.create_table("transcripts", *record(), source_fk(unique=True),
                    sa.Column("provider", sa.String(120), nullable=False),
                    sa.Column("model", sa.String(160), nullable=False),
                    sa.Column("language", sa.String(32), nullable=False),
                    sa.Column("topics", sa.JSON(), nullable=False),
                    sa.Column("analysis_provider", sa.String(120)), sa.Column("analysis_model", sa.String(160)))
    op.create_table("transcript_segments", *record(),
                    sa.Column("transcript_id", sa.Uuid(), sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("position", sa.Integer(), nullable=False), sa.Column("start", sa.Float(), nullable=False),
                    sa.Column("end", sa.Float(), nullable=False), sa.Column("text", sa.Text(), nullable=False),
                    sa.UniqueConstraint("transcript_id", "position"), sa.CheckConstraint('"end" > start AND start >= 0'))
    op.create_table("content_segments", *record(), source_fk(),
                    sa.Column("job_id", sa.Uuid(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("first", sa.Integer(), nullable=False), sa.Column("last", sa.Integer(), nullable=False),
                    sa.Column("start", sa.Float(), nullable=False), sa.Column("end", sa.Float(), nullable=False),
                    *(sa.Column(key, sa.Text(), nullable=False) for key in
                      ("title", "hook", "description", "topic", "reason", "transcript_text")),
                    sa.Column("provider", sa.String(120), nullable=False), sa.Column("model", sa.String(160), nullable=False),
                    sa.Column("status", sa.String(16), nullable=False),
                    sa.CheckConstraint('"end" > start AND start >= 0'),
                    sa.CheckConstraint("status in ('suggested','approved','rejected')"))
    op.create_index("ix_content_segments_source_id", "content_segments", ["source_id"])


def downgrade():
    op.drop_table("content_segments")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")
    op.execute("DELETE FROM processing_jobs WHERE kind <> 'ingest'")
    for name in ("ix_job_queue", "uq_job_active_source", "uq_job_ingest_source"):
        op.drop_index(name, table_name="processing_jobs")
    with op.batch_alter_table("processing_jobs") as batch:
        for name in ("lease_until", "lease_token", "error", "progress", "attempt", "stage"):
            batch.drop_column(name)
        batch.alter_column("finished_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_unique_constraint("uq_processing_jobs_source_id", ["source_id"])
