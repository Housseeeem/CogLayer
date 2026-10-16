"""Application settings for CogLayer.

Settings are loaded from environment variables (prefixed with ``COGLAYER_``),
a ``.env`` file, or fall back to the defaults defined here.  The module
exposes a ``get_settings()`` factory decorated with :func:`functools.lru_cache`
so the ``Settings`` object is constructed at most once per process.

Usage::

    from coglayer.core.settings import get_settings

    settings = get_settings()
    print(settings.db_path)
"""

import functools

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration for the CogLayer application.

    All fields can be overridden by setting the corresponding environment
    variable (case-insensitive, optionally prefixed with ``COGLAYER_``).

    Fields:
        db_path: Path to the SQLite database file (R-005.6).
        completeness_threshold: Minimum ``data_quality.completeness`` a task
            result must reach before the Decision Engine counts it as
            sufficient (R-007.2).  Must be in [0, 1].
        forgetting_factor: lambda applied to the Beta distribution before each
            profile update: ``alpha = 1 + lambda*(alpha - 1)``, ``beta = 1 + lambda*(beta - 1)``.
            Controls how quickly older evidence is discounted (R-006.3).
        llm_provider: Identifier for the LLM backend.  ``"fake"`` selects the
            deterministic :class:`coglayer.providers.fake.FakeProvider` used
            in tests and offline demos (R-005.6).
    """

    db_path: str = "coglayer.db"
    completeness_threshold: float = 0.8
    forgetting_factor: float = 0.98
    llm_provider: str = "fake"
    # Quality gate: minimum Go accuracy required for go_no_go to update the profile.
    # This threshold is a design choice with no source: at least 11 correct Go out of 15 (0.7).
    go_no_go_min_go_accuracy: float = 0.7

    @property
    def go_accuracy_threshold(self) -> float:
        """Alias for go_no_go_min_go_accuracy."""
        return self.go_no_go_min_go_accuracy

    model_config = {"env_prefix": "COGLAYER_", "env_file": ".env", "extra": "ignore"}


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application :class:`Settings`, constructing it at most once.

    The result is cached with :func:`functools.lru_cache` so repeated calls
    within a process share a single ``Settings`` instance.  To force a fresh
    read (e.g. in tests), call ``get_settings.cache_clear()`` first.

    Returns:
        The singleton :class:`Settings` instance.
    """
    return Settings()
