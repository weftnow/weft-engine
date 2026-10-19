from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Environment, Settings


def test_environment_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("WEFT_LOG_LEVEL=WARNING\nWEFT_ENVIRONMENT=test\n")
    monkeypatch.setenv("WEFT_LOG_LEVEL", "ERROR")
    settings = Settings(_env_file=dotenv)
    assert settings.environment is Environment.TEST
    assert settings.log_level == "ERROR"


def test_production_requires_explicit_docs_disable() -> None:
    with pytest.raises(ValidationError, match="WEFT_DOCS_ENABLED=false"):
        Settings(_env_file=None, environment=Environment.PRODUCTION, docs_enabled=True)


@pytest.mark.parametrize(
    ("name", "value"),
    [("WEFT_ENVIRONMENT", "staging-typo"), ("WEFT_LOG_LEVEL", "SECRET")],
)
def test_invalid_environment_values_fail_startup(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
