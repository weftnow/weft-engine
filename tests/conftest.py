import pytest


@pytest.fixture(autouse=True)
def isolated_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Never let the developer's working directory or settings change test behavior."""
    for name in ("WEFT_ENVIRONMENT", "WEFT_DOCS_ENABLED", "WEFT_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path_factory.mktemp("runtime"))
