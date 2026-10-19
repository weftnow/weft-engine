"""F07 change consumption: receipts, batches, feed entries, and recommendation revocation."""

# ruff: noqa: E501

from alembic import op

revision = "0002_f07"
down_revision = "0001_f06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE weft_engine.matching_change_batches (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(), attempt integer NOT NULL DEFAULT 1,
          next_attempt_at timestamptz, state varchar(16) NOT NULL DEFAULT 'scheduled',
          last_run_id uuid REFERENCES weft_engine.matching_runs(id), abandon_reason varchar(80),
          CONSTRAINT matching_change_batches_state CHECK (state IN ('scheduled','completed','abandoned'))
        )
    """)
    op.execute(
        "CREATE INDEX matching_change_batches_event_idx ON weft_engine.matching_change_batches(organization_id,event_id,state)"
    )
    op.execute("""
        ALTER TABLE weft_engine.matching_runs
          ADD COLUMN trigger varchar(16) NOT NULL DEFAULT 'api',
          ADD COLUMN change_batch_id uuid REFERENCES weft_engine.matching_change_batches(id),
          ADD CONSTRAINT matching_runs_trigger_valid CHECK (trigger IN ('api','change'))
    """)
    op.execute(
        "CREATE INDEX matching_runs_event_idx ON weft_engine.matching_runs(organization_id,event_id,created_at)"
    )
    op.execute("""
        CREATE TABLE weft_engine.matching_change_receipts (
          change_id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          kind varchar(48) NOT NULL, guest_ids uuid[] NOT NULL, change_created_at timestamptz NOT NULL,
          received_at timestamptz NOT NULL DEFAULT now(),
          batch_id uuid REFERENCES weft_engine.matching_change_batches(id)
        )
    """)
    op.execute(
        "CREATE INDEX matching_change_receipts_event_idx ON weft_engine.matching_change_receipts(event_id,batch_id,change_created_at)"
    )
    op.execute("""
        ALTER TABLE weft_engine.recommendations
          ADD COLUMN revoked_at timestamptz,
          ADD COLUMN revocation_reason varchar(48),
          ADD COLUMN revoked_by_run_id uuid REFERENCES weft_engine.matching_runs(id),
          ADD CONSTRAINT recommendations_revocation_reason_valid CHECK (revocation_reason IS NULL OR revocation_reason IN ('guest_excluded','pair_blocked','identity_resolution_required','guest_missing')),
          ADD CONSTRAINT recommendations_revocation_consistent CHECK ((revoked_at IS NULL) = (revocation_reason IS NULL))
    """)
    op.execute("""
        CREATE TABLE weft_engine.matching_feed_entries (
          seq bigserial PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          kind varchar(16) NOT NULL,
          recommendation_id uuid NOT NULL REFERENCES weft_engine.recommendations(id),
          run_id uuid REFERENCES weft_engine.matching_runs(id),
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT matching_feed_entries_kind CHECK (kind IN ('issued','revoked')),
          CONSTRAINT matching_feed_entries_once UNIQUE (recommendation_id, kind)
        )
    """)
    op.execute(
        "CREATE INDEX matching_feed_entries_event_idx ON weft_engine.matching_feed_entries(organization_id,event_id,seq)"
    )
    # F06 recommendations predate the feed; give consumers an 'issued' entry for each.
    op.execute("""
        INSERT INTO weft_engine.matching_feed_entries(organization_id,event_id,kind,recommendation_id,run_id,created_at)
        SELECT organization_id,event_id,'issued',id,source_run_id,created_at
        FROM weft_engine.recommendations ORDER BY created_at, id
    """)


def downgrade() -> None:
    op.execute("DROP TABLE weft_engine.matching_feed_entries")
    op.execute("""
        ALTER TABLE weft_engine.recommendations
          DROP CONSTRAINT recommendations_revocation_consistent,
          DROP CONSTRAINT recommendations_revocation_reason_valid,
          DROP COLUMN revoked_by_run_id, DROP COLUMN revocation_reason, DROP COLUMN revoked_at
    """)
    op.execute("DROP TABLE weft_engine.matching_change_receipts")
    op.execute("DROP INDEX weft_engine.matching_runs_event_idx")
    op.execute("""
        ALTER TABLE weft_engine.matching_runs
          DROP CONSTRAINT matching_runs_trigger_valid,
          DROP COLUMN change_batch_id, DROP COLUMN trigger
    """)
    op.execute("DROP TABLE weft_engine.matching_change_batches")
