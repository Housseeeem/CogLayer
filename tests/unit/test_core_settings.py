"""Unit tests for coglayer.core.settings.

Covers:
- Default values are correct.
- Environment variable overrides work (via monkeypatch).
- get_settings() cache is cleared between tests that create fresh Settings.

Requirements: R-002.4 (settings support the core data layer and task contracts)
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from coglayer.core.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    """Clear the lru_cache before every test so each test starts fresh."""
    get_settings.cache_clear()
    yield
    # Also clear after to avoid polluting subsequent tests.
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_ENV_KEYS = (
    "COGLAYER_DB_PATH",
    "COGLAYER_LLM_PROVIDER",
    "COGLAYER_COMPLETENESS_THRESHOLD",
    "COGLAYER_FORGETTING_FACTOR",
    "COGLAYER_GO_NO_GO_MIN_GO_ACCURACY",
    "COGLAYER_COACH_USE_LLM",
)


def _clear_coglayer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all COGLAYER_ env vars so defaults are tested cleanly."""
    for key in _ALL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestSettingsDefaults:
    def test_db_path_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_coglayer_env(monkeypatch)
        settings = Settings(_env_file=None)
        assert settings.db_path == "coglayer.db"

    def test_completeness_threshold_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_coglayer_env(monkeypatch)
        settings = Settings(_env_file=None)
        assert settings.completeness_threshold == pytest.approx(0.8)

    def test_forgetting_factor_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_coglayer_env(monkeypatch)
        settings = Settings(_env_file=None)
        assert settings.forgetting_factor == pytest.approx(0.98)

    def test_llm_provider_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_coglayer_env(monkeypatch)
        settings = Settings(_env_file=None)
        assert settings.llm_provider == "fake"

    def test_go_no_go_min_go_accuracy_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_coglayer_env(monkeypatch)
        settings = Settings(_env_file=None)
        assert settings.go_no_go_min_go_accuracy == pytest.approx(0.7)

    def test_coach_use_llm_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_coglayer_env(monkeypatch)
        settings = Settings(_env_file=None)
        assert settings.coach_use_llm is False


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestSettingsEnvOverrides:
    def test_db_path_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        db_file = str(tmp_path / "test.db")
        monkeypatch.setenv("COGLAYER_DB_PATH", db_file)
        get_settings.cache_clear()
        settings = get_settings(_env_file=".env")
        assert settings.db_path == db_file

    def test_llm_provider_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COGLAYER_LLM_PROVIDER", "openai")
        get_settings.cache_clear()
        settings = get_settings(_env_file=".env")
        assert settings.llm_provider == "openai"

    def test_completeness_threshold_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COGLAYER_COMPLETENESS_THRESHOLD", "0.9")
        get_settings.cache_clear()
        settings = get_settings(_env_file=".env")
        assert settings.completeness_threshold == pytest.approx(0.9)

    def test_forgetting_factor_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COGLAYER_FORGETTING_FACTOR", "0.95")
        get_settings.cache_clear()
        settings = get_settings(_env_file=".env")
        assert settings.forgetting_factor == pytest.approx(0.95)

    def test_go_no_go_min_go_accuracy_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COGLAYER_GO_NO_GO_MIN_GO_ACCURACY", "0.75")
        get_settings.cache_clear()
        settings = get_settings(_env_file=".env")
        assert settings.go_no_go_min_go_accuracy == pytest.approx(0.75)

    def test_coach_use_llm_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COGLAYER_COACH_USE_LLM", "true")
        get_settings.cache_clear()
        settings = get_settings(_env_file=".env")
        assert settings.coach_use_llm is True


# ---------------------------------------------------------------------------
# get_settings() caching behaviour
# ---------------------------------------------------------------------------


class TestGetSettingsCache:
    def test_returns_same_instance_on_repeat_calls(self) -> None:
        s1 = get_settings(_env_file=".env")
        s2 = get_settings(_env_file=".env")
        assert s1 is s2

    def test_cache_clear_allows_new_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s1 = get_settings()
        get_settings.cache_clear()
        monkeypatch.setenv("COGLAYER_LLM_PROVIDER", "anthropic")
        s2 = get_settings(_env_file=".env")
        # After clearing the cache the provider should pick up the new env var.
        assert s2.llm_provider == "anthropic"
        # The two instances are different objects.
        assert s1 is not s2

    def test_defaults_returned_without_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Ensure no COGLAYER_ vars are set in this test.
        for key in (
            "COGLAYER_DB_PATH",
            "COGLAYER_LLM_PROVIDER",
            "COGLAYER_COMPLETENESS_THRESHOLD",
            "COGLAYER_FORGETTING_FACTOR",
            "COGLAYER_GO_NO_GO_MIN_GO_ACCURACY",
            "COGLAYER_COACH_USE_LLM",
        ):
            monkeypatch.delenv(key, raising=False)
        get_settings.cache_clear()
        settings = Settings(_env_file=None)
        assert settings.db_path == "coglayer.db"
        assert settings.llm_provider == "fake"
        assert settings.completeness_threshold == pytest.approx(0.8)
        assert settings.forgetting_factor == pytest.approx(0.98)
        assert settings.go_no_go_min_go_accuracy == pytest.approx(0.7)
        assert settings.coach_use_llm is False
