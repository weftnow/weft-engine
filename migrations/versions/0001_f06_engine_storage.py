"""Initial isolated F06 storage."""

# ruff: noqa: E501

from alembic import op

revision = "0001_f06"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS weft_engine")
    op.execute("""
        CREATE TABLE weft_engine.matching_runs (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          idempotency_key varchar(200) NOT NULL, mode varchar(16) NOT NULL,
          target_guest_id uuid, status varchar(32) NOT NULL, snapshot jsonb NOT NULL,
          fingerprint varchar(64) NOT NULL, progress jsonb NOT NULL DEFAULT '{}'::jsonb,
          provenance jsonb NOT NULL DEFAULT '{}'::jsonb, usage jsonb NOT NULL DEFAULT '{}'::jsonb,
          failure_code varchar(80), failure_message varchar(500), lease_owner varchar(120),
          lease_expires_at timestamptz, heartbeat_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz,
          CONSTRAINT matching_runs_mode_valid CHECK (mode IN ('event','more')),
          CONSTRAINT matching_runs_status_valid CHECK (status IN ('waiting','running','failed','finished','invalid_result')),
          CONSTRAINT matching_runs_idempotency_unique UNIQUE (organization_id,event_id,idempotency_key)
        )
    """)
    op.execute(
        "CREATE INDEX matching_runs_queue_idx ON weft_engine.matching_runs(status,created_at)"
    )
    op.execute("""
        CREATE TABLE weft_engine.matching_attempts (
          id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES weft_engine.matching_runs(id) ON DELETE CASCADE,
          kind varchar(32) NOT NULL, status varchar(32) NOT NULL, model varchar(160) NOT NULL,
          prompt_version varchar(100) NOT NULL, input_fingerprint varchar(64) NOT NULL,
          provider_response_id varchar(200), input_tokens integer NOT NULL DEFAULT 0,
          output_tokens integer NOT NULL DEFAULT 0, estimated_cost_usd numeric(12,6) NOT NULL DEFAULT 0,
          error_code varchar(80), created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
        )
    """)
    op.execute(
        "CREATE INDEX matching_attempts_run_idx ON weft_engine.matching_attempts(run_id,created_at)"
    )
    op.execute("""
        CREATE TABLE weft_engine.matching_embeddings (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL, guest_id uuid NOT NULL,
          channel varchar(32) NOT NULL, content_fingerprint varchar(64) NOT NULL, model varchar(160) NOT NULL,
          dimensions integer NOT NULL, values double precision[] NOT NULL,
          live_attempt_id uuid NOT NULL REFERENCES weft_engine.matching_attempts(id),
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT matching_embeddings_cache_unique UNIQUE(organization_id,guest_id,channel,content_fingerprint,model)
        )
    """)
    op.execute("""
        CREATE TABLE weft_engine.recommendations (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          guest_low_id uuid NOT NULL, guest_high_id uuid NOT NULL, source_run_id uuid NOT NULL REFERENCES weft_engine.matching_runs(id),
          profile_versions jsonb NOT NULL, directional_scores jsonb NOT NULL, pair_score integer NOT NULL,
          benefits jsonb NOT NULL, evidence jsonb NOT NULL, missing_information jsonb NOT NULL,
          uncertainty text NOT NULL, shareable_reasons jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT recommendations_pair_order CHECK (guest_low_id < guest_high_id),
          CONSTRAINT recommendations_score_valid CHECK (pair_score BETWEEN 70 AND 100),
          CONSTRAINT recommendations_pair_unique UNIQUE(event_id,guest_low_id,guest_high_id)
        )
    """)
    op.execute(
        "CREATE INDEX recommendations_event_idx ON weft_engine.recommendations(organization_id,event_id,created_at)"
    )
    op.execute("""
        CREATE TABLE weft_engine.matching_slot_grants (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL, guest_id uuid NOT NULL,
          request_key varchar(200) NOT NULL, slots integer NOT NULL DEFAULT 3,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT matching_slot_grants_request_unique UNIQUE(organization_id,event_id,request_key),
          CONSTRAINT matching_slot_grants_slots_valid CHECK(slots=3)
        )
    """)
    op.execute("""
        CREATE TABLE weft_engine.matching_evaluations (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL, event_id uuid NOT NULL,
          pair_fingerprint varchar(64) NOT NULL, model varchar(160) NOT NULL, prompt_version varchar(100) NOT NULL,
          policy_version varchar(100) NOT NULL, live_attempt_id uuid NOT NULL REFERENCES weft_engine.matching_attempts(id),
          evaluation jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT matching_evaluations_cache_unique UNIQUE(organization_id,pair_fingerprint,model,prompt_version,policy_version)
        )
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA weft_engine CASCADE")
