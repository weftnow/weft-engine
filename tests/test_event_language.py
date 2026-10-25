from __future__ import annotations

from typing import Any
from uuid import UUID

from src.matching.models import Run
from src.matching.storage import create_run, event_language, fingerprint, run_payload
from src.matching.worker import LANGUAGE_INSTRUCTIONS

ORG = UUID("10000000-0000-0000-0000-000000000001")
EVENT = UUID("20000000-0000-0000-0000-000000000001")


def snapshot(language: object = "en") -> dict[str, Any]:
    event: dict[str, Any] = {"id": str(EVENT), "name": "Launch", "city": "Singapore"}
    if language is not None:
        event["language"] = language
    return {"event": event, "guests": []}


class FakeSession:
    """Just enough of an async session for create_run: no prior run, collect what is added."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def scalar(self, *_: object, **__: object) -> None:
        return None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


def test_event_language_accepts_supported_languages_and_falls_back_to_english() -> None:
    assert event_language(snapshot("es")) == "es"
    assert event_language(snapshot("en")) == "en"
    assert event_language(snapshot("fr")) == "en"
    assert event_language(snapshot(None)) == "en"
    assert event_language({}) == "en"


def test_snapshot_fingerprint_changes_when_the_language_changes() -> None:
    english = fingerprint(run_payload(snapshot("en"), {}, "policy-v1"))
    spanish = fingerprint(run_payload(snapshot("es"), {}, "policy-v1"))
    assert english != spanish
    assert fingerprint(run_payload(snapshot("es"), {}, "policy-v1")) == spanish


def test_verification_prompt_requires_spanish_with_verbatim_quotes() -> None:
    spanish = LANGUAGE_INSTRUCTIONS["es"]
    assert "Spanish" in spanish
    assert "exactly as it appears" in spanish
    assert "reason codes" in spanish
    assert "English" in LANGUAGE_INSTRUCTIONS["en"]
    assert set(LANGUAGE_INSTRUCTIONS) == {"en", "es"}


async def test_run_provenance_records_the_event_language() -> None:
    for language in ("en", "es"):
        session = FakeSession()
        run = await create_run(
            session,  # type: ignore[arg-type]
            organization_id=ORG,
            event_id=EVENT,
            idempotency_key=f"key-{language}",
            mode="event",
            target_guest_id=None,
            payload=run_payload(snapshot(language), {}, "policy-v1"),
            provenance={"policy_version": "policy-v1"},
        )
        assert isinstance(run, Run)
        assert run.provenance["language"] == language
        assert run.provenance["policy_version"] == "policy-v1"
