"""Durable per-provider-attempt budget reservations."""

from alembic import op

revision = "0003_matching_budget"
down_revision = "0002_f07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE weft_engine.matching_budget_reservations (
          attempt_id uuid PRIMARY KEY REFERENCES weft_engine.matching_attempts(id)
            ON DELETE CASCADE,
          run_id uuid NOT NULL REFERENCES weft_engine.matching_runs(id) ON DELETE CASCADE,
          reserved_cost_usd numeric(12,6) NOT NULL CHECK (reserved_cost_usd >= 0),
          actual_cost_usd numeric(12,6),
          state varchar(16) NOT NULL CHECK (state IN ('reserved','settled','unknown')),
          created_at timestamptz NOT NULL DEFAULT now(), settled_at timestamptz
        )
    """)
    op.execute("""
        CREATE INDEX matching_budget_reservations_run_idx
        ON weft_engine.matching_budget_reservations(run_id,state)
    """)
    op.execute("""
        CREATE TABLE weft_engine.matching_verifications (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          input_fingerprint varchar(64) NOT NULL, privacy_fingerprint varchar(64) NOT NULL,
          model varchar(160) NOT NULL, verifier_version varchar(100) NOT NULL,
          live_attempt_id uuid NOT NULL REFERENCES weft_engine.matching_attempts(id),
          result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT matching_verifications_cache_unique UNIQUE
            (organization_id,event_id,input_fingerprint,privacy_fingerprint,model,verifier_version)
        )
    """)
    op.execute("""
        CREATE TABLE weft_engine.matching_screenings (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          input_fingerprint varchar(64) NOT NULL, model varchar(160) NOT NULL,
          screening_version varchar(100) NOT NULL,
          live_attempt_id uuid NOT NULL REFERENCES weft_engine.matching_attempts(id),
          result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT matching_screenings_cache_unique UNIQUE
            (organization_id,event_id,input_fingerprint,model,screening_version)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE weft_engine.matching_screenings")
    op.execute("DROP TABLE weft_engine.matching_verifications")
    op.execute("DROP TABLE weft_engine.matching_budget_reservations")
