"""Unit tests for InMemoryTaskRegistry and build_default_registry.

Requirements: R-002.1, R-002.5
"""

import pytest

from coglayer.core.models import TaskDescriptor
from coglayer.signals.registry import InMemoryTaskRegistry, build_default_registry

# ---------------------------------------------------------------------------
# InMemoryTaskRegistry — basic contract
# ---------------------------------------------------------------------------


class TestInMemoryTaskRegistry:
    def test_register_and_get_roundtrip(self) -> None:
        """Registered descriptor is retrievable by (task_id, version)."""
        registry = InMemoryTaskRegistry()
        descriptor = TaskDescriptor(
            task_id="dummy",
            version="0.1",
            instructions="Do something.",
            target_dimensions=["dim_a"],
            parameters={"n": 5},
        )
        registry.register(descriptor)
        result = registry.get("dummy", "0.1")
        assert result == descriptor

    def test_get_raises_key_error_when_not_found(self) -> None:
        """get() raises KeyError for an unregistered (task_id, version)."""
        registry = InMemoryTaskRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent", "1.0")

    def test_get_raises_key_error_wrong_version(self) -> None:
        """get() raises KeyError when the version doesn't match."""
        registry = InMemoryTaskRegistry()
        descriptor = TaskDescriptor(
            task_id="task_x",
            version="1.0",
            instructions="...",
            target_dimensions=[],
            parameters={},
        )
        registry.register(descriptor)
        with pytest.raises(KeyError):
            registry.get("task_x", "2.0")

    def test_list_ids_returns_distinct_task_ids(self) -> None:
        """list_ids() returns unique task_ids even when multiple versions exist."""
        registry = InMemoryTaskRegistry()
        for version in ("1.0", "1.1", "2.0"):
            registry.register(
                TaskDescriptor(
                    task_id="repeated_task",
                    version=version,
                    instructions="...",
                    target_dimensions=[],
                    parameters={},
                )
            )
        registry.register(
            TaskDescriptor(
                task_id="other_task",
                version="1.0",
                instructions="...",
                target_dimensions=[],
                parameters={},
            )
        )
        ids = registry.list_ids()
        assert sorted(ids) == ["other_task", "repeated_task"]
        # No duplicates
        assert len(ids) == len(set(ids))

    def test_list_ids_empty_registry(self) -> None:
        """list_ids() returns an empty list for an empty registry."""
        registry = InMemoryTaskRegistry()
        assert registry.list_ids() == []

    def test_register_overwrites_existing_version(self) -> None:
        """Registering the same (task_id, version) replaces the previous entry."""
        registry = InMemoryTaskRegistry()
        original = TaskDescriptor(
            task_id="task_a",
            version="1.0",
            instructions="original",
            target_dimensions=[],
            parameters={},
        )
        updated = TaskDescriptor(
            task_id="task_a",
            version="1.0",
            instructions="updated",
            target_dimensions=[],
            parameters={},
        )
        registry.register(original)
        registry.register(updated)
        assert registry.get("task_a", "1.0").instructions == "updated"


# ---------------------------------------------------------------------------
# build_default_registry — pre-populated factory
# ---------------------------------------------------------------------------


class TestBuildDefaultRegistry:
    def test_returns_inmemorytaskregistry(self) -> None:
        """Factory returns an InMemoryTaskRegistry instance."""
        registry = build_default_registry()
        assert isinstance(registry, InMemoryTaskRegistry)

    def test_go_no_go_registered(self) -> None:
        """go_no_go v1.0 is present in the default registry."""
        registry = build_default_registry()
        descriptor = registry.get("go_no_go", "1.0")
        assert descriptor.task_id == "go_no_go"
        assert descriptor.version == "1.0"
        assert "response_inhibition" in descriptor.target_dimensions

    def test_sequence_span_registered(self) -> None:
        """sequence_span v1.0 is present in the default registry."""
        registry = build_default_registry()
        descriptor = registry.get("sequence_span", "1.0")
        assert descriptor.task_id == "sequence_span"
        assert descriptor.version == "1.0"
        assert "sequential_visual_memory" in descriptor.target_dimensions

    def test_list_ids_contains_both_built_in_tasks(self) -> None:
        """list_ids() returns both built-in task IDs."""
        registry = build_default_registry()
        ids = registry.list_ids()
        assert "go_no_go" in ids
        assert "sequence_span" in ids

    def test_go_no_go_parameters(self) -> None:
        """Go/No-Go descriptor has the expected default parameters."""
        registry = build_default_registry()
        params = registry.get("go_no_go", "1.0").parameters
        assert params["n_practice_trials"] == 5
        assert params["n_scored_trials"] == 20
        assert params["nogo_proportion"] == 0.25
        assert params["isi_ms"] == 800

    def test_sequence_span_parameters(self) -> None:
        """Sequence Span descriptor has the expected default parameters."""
        registry = build_default_registry()
        params = registry.get("sequence_span", "1.0").parameters
        assert params["n_demo_sequences"] == 1
        assert params["n_practice_sequences"] == 2
        assert params["starting_length"] == 3
        assert params["increment"] == 1
        assert params["max_length"] == 9
        assert params["max_rt_ms"] == 30000

    def test_default_registry_is_independent_per_call(self) -> None:
        """Each call to build_default_registry() returns a fresh instance."""
        r1 = build_default_registry()
        r2 = build_default_registry()
        assert r1 is not r2
        # Mutating one does not affect the other
        r1.register(
            TaskDescriptor(
                task_id="extra",
                version="1.0",
                instructions="...",
                target_dimensions=[],
                parameters={},
            )
        )
        assert "extra" not in r2.list_ids()
