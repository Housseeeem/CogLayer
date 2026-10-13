"""In-memory task registry for CogLayer.

Provides ``InMemoryTaskRegistry``, a concrete implementation of the
``TaskRegistry`` Protocol defined in ``core.protocols``, and a
``build_default_registry()`` factory that returns a pre-populated registry
with the two built-in cognitive tasks (Go/No-Go and Sequence Span).

Adding a new task requires only a call to ``register()`` (or a new entry in
``build_default_registry()``); no changes to profiling, decision, or coach
code are needed (R-002.5).

Requirements: R-002.1, R-002.5
"""

from __future__ import annotations

from coglayer.core.models import TaskDescriptor

__all__ = [
    "InMemoryTaskRegistry",
    "build_default_registry",
]


class InMemoryTaskRegistry:
    """Concrete in-memory implementation of the ``TaskRegistry`` Protocol.

    Tasks are keyed by ``(task_id, version)`` tuples.  Multiple versions of
    the same task may coexist in the registry without collision.

    Requirements: R-002.1, R-002.5
    """

    def __init__(self) -> None:
        # Internal store: (task_id, version) → TaskDescriptor
        self._store: dict[tuple[str, str], TaskDescriptor] = {}

    def register(self, descriptor: TaskDescriptor) -> None:
        """Store a task descriptor under its ``(task_id, version)`` key.

        If a descriptor with the same ``(task_id, version)`` already exists it
        is silently replaced, allowing re-registration during tests.

        Args:
            descriptor: The task descriptor to register.
        """
        key = (descriptor.task_id, descriptor.version)
        self._store[key] = descriptor

    def get(self, task_id: str, version: str) -> TaskDescriptor:
        """Retrieve a descriptor by ``task_id`` and ``version``.

        Args:
            task_id: The task identifier.
            version: The task version string.

        Returns:
            The matching ``TaskDescriptor``.

        Raises:
            KeyError: If no descriptor matches the ``(task_id, version)`` pair.
        """
        key = (task_id, version)
        if key not in self._store:
            raise KeyError(f"No task registered for task_id={task_id!r}, version={version!r}")
        return self._store[key]

    def list_ids(self) -> list[str]:
        """Return a list of distinct registered ``task_id`` values.

        Versions are collapsed: if the same ``task_id`` is registered under
        multiple versions it appears only once in the result.

        Returns:
            A sorted list of unique task identifiers.
        """
        return sorted({task_id for task_id, _version in self._store})


# ---------------------------------------------------------------------------
# Built-in task descriptors
# ---------------------------------------------------------------------------

_GO_NO_GO_DESCRIPTOR = TaskDescriptor(
    task_id="go_no_go",
    version="1.0",
    instructions=(
        "A series of stimuli will appear on screen. "
        "Press the spacebar as quickly as possible when you see the Go stimulus (green circle), "
        "but do NOT press anything when you see the No-Go stimulus (red circle). "
        "Try to respond accurately and quickly. "
        "This is a non-clinical measure of response speed and inhibition."
    ),
    target_dimensions=["response_inhibition"],
    parameters={
        "n_practice_trials": 5,
        "n_scored_trials": 20,
        "nogo_proportion": 0.25,
        "isi_ms": 800,
    },
)

_SEQUENCE_SPAN_DESCRIPTOR = TaskDescriptor(
    task_id="sequence_span",
    version="1.0",
    instructions=(
        "A sequence of squares will light up one at a time. "
        "Watch the full sequence, then reproduce it by clicking the squares in the same order. "
        "The sequences will get longer as you go. "
        "This task measures sequential visual memory via spatial sequence reproduction. "
        "It is used as a proxy for working-memory capacity"
        " but does not purely measure working memory. "
        "This is a non-clinical measure."
    ),
    target_dimensions=["sequential_visual_memory"],
    parameters={
        "n_demo_sequences": 1,
        "n_practice_sequences": 2,
        "starting_length": 3,
        "increment": 1,
        "max_length": 9,
        "max_rt_ms": 30000,
    },
)


def build_default_registry() -> InMemoryTaskRegistry:
    """Return a pre-populated ``InMemoryTaskRegistry`` with the built-in tasks.

    Built-in tasks:
    - **Go/No-Go** (``task_id="go_no_go"``, ``version="1.0"``) — measures
      response inhibition via a go/no-go paradigm.
    - **Sequence Span** (``task_id="sequence_span"``, ``version="1.0"``) —
      measures sequential visual memory via spatial sequence reproduction
      (proxy for working-memory capacity; does not purely measure working memory).

    Returns:
        A ready-to-use ``InMemoryTaskRegistry`` instance.

    Requirements: R-002.1, R-002.5
    """
    registry = InMemoryTaskRegistry()
    registry.register(_GO_NO_GO_DESCRIPTOR)
    registry.register(_SEQUENCE_SPAN_DESCRIPTOR)
    return registry
