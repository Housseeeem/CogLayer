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

from typing import TYPE_CHECKING

from coglayer.core.models import TaskDescriptor
from coglayer.core.tasks import (
    CORSI_BLOCKS_DESCRIPTOR,
    DIGIT_SPAN_DESCRIPTOR,
    GO_NO_GO_DESCRIPTOR,
    LETTER_NUMBER_DESCRIPTOR,
    N_BACK_DESCRIPTOR,
    PERCEPTION_DESCRIPTOR,
    SEQUENCE_SPAN_DESCRIPTOR,
    STROOP_DESCRIPTOR,
)

if TYPE_CHECKING:
    from coglayer.core.protocols import ScoringAdapter

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
        # Scorer store: task_id → ScoringAdapter
        self._scorers: dict[str, ScoringAdapter] = {}

    def register(
        self,
        descriptor: TaskDescriptor,
        scorer: ScoringAdapter | None = None,
    ) -> None:
        """Store a task descriptor under its ``(task_id, version)`` key.

        If a descriptor with the same ``(task_id, version)`` already exists it
        is silently replaced, allowing re-registration during tests.

        Args:
            descriptor: The task descriptor to register.
            scorer: Optional scoring adapter associated with this task.
        """
        key = (descriptor.task_id, descriptor.version)
        self._store[key] = descriptor
        if scorer is not None:
            self._scorers[descriptor.task_id] = scorer

    def register_scorer(self, task_id: str, scorer: ScoringAdapter) -> None:
        """Register a scoring adapter for a task_id."""
        self._scorers[task_id] = scorer

    def get_scorer(self, task_id: str) -> ScoringAdapter | None:
        """Get the scoring adapter for task_id, if registered."""
        return self._scorers.get(task_id)

    def get_scorers(self) -> dict[str, ScoringAdapter]:
        """Return a copy of all registered scoring adapters."""
        return dict(self._scorers)

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

    def get_descriptor(self, task_id: str) -> TaskDescriptor:
        """Retrieve the latest registered TaskDescriptor for task_id.

        Args:
            task_id: The task identifier.

        Returns:
            The matching ``TaskDescriptor``.

        Raises:
            KeyError: If no task matches task_id.
        """
        matching = [desc for (tid, _), desc in self._store.items() if tid == task_id]
        if not matching:
            raise KeyError(f"No task registered for task_id={task_id!r}")
        return matching[-1]

    def list_descriptors(self) -> list[TaskDescriptor]:
        """Return all unique registered task descriptors (latest per task_id).

        Descriptors are sorted alphabetically by task_id.

        Returns:
            A list of TaskDescriptor objects ordered alphabetically by task_id.
        """
        descriptors: list[TaskDescriptor] = []
        for task_id in self.list_ids():
            descriptors.append(self.get_descriptor(task_id))
        return descriptors


# ---------------------------------------------------------------------------
# Built-in task descriptors (referenced from core.tasks single source of truth)
# ---------------------------------------------------------------------------

_GO_NO_GO_DESCRIPTOR = GO_NO_GO_DESCRIPTOR
_SEQUENCE_SPAN_DESCRIPTOR = SEQUENCE_SPAN_DESCRIPTOR


def build_default_registry() -> InMemoryTaskRegistry:
    """Return a pre-populated ``InMemoryTaskRegistry`` with the built-in tasks.

    Built-in tasks:
    - **Go/No-Go** (``task_id="go_no_go"``)
    - **Sequence Span** (``task_id="sequence_span"``)
    - **Digit Span** (``task_id="digit_span"``)
    - **Stroop** (``task_id="stroop"``)
    - **Corsi Blocks** (``task_id="corsi_blocks"``)
    - **N-Back** (``task_id="n_back"``)
    - **Letter-Number Sequencing** (``task_id="letter_number_sequencing"``)
    - **Perception Lab** (``task_id="perception_lab"``)

    Returns:
        A ready-to-use ``InMemoryTaskRegistry`` instance.

    Requirements: R-002.1, R-002.5
    """
    from coglayer.signals.corsi_blocks import CorsiBlocksScorer
    from coglayer.signals.digit_span import DigitSpanScorer
    from coglayer.signals.go_no_go import GoNoGoScorer
    from coglayer.signals.letter_number import LetterNumberSequencingScorer
    from coglayer.signals.n_back import NBackScorer
    from coglayer.signals.perception import PerceptionScorer
    from coglayer.signals.sequence_span import SequenceSpanScorer
    from coglayer.signals.stroop import StroopScorer

    registry = InMemoryTaskRegistry()
    registry.register(
        GO_NO_GO_DESCRIPTOR,
        scorer=GoNoGoScorer(descriptor=GO_NO_GO_DESCRIPTOR),
    )
    registry.register(
        SEQUENCE_SPAN_DESCRIPTOR,
        scorer=SequenceSpanScorer(descriptor=SEQUENCE_SPAN_DESCRIPTOR),
    )
    registry.register(
        DIGIT_SPAN_DESCRIPTOR,
        scorer=DigitSpanScorer(descriptor=DIGIT_SPAN_DESCRIPTOR),
    )
    registry.register(
        STROOP_DESCRIPTOR,
        scorer=StroopScorer(descriptor=STROOP_DESCRIPTOR),
    )
    registry.register(
        CORSI_BLOCKS_DESCRIPTOR,
        scorer=CorsiBlocksScorer(descriptor=CORSI_BLOCKS_DESCRIPTOR),
    )
    registry.register(
        N_BACK_DESCRIPTOR,
        scorer=NBackScorer(descriptor=N_BACK_DESCRIPTOR),
    )
    registry.register(
        LETTER_NUMBER_DESCRIPTOR,
        scorer=LetterNumberSequencingScorer(descriptor=LETTER_NUMBER_DESCRIPTOR),
    )
    registry.register(
        PERCEPTION_DESCRIPTOR,
        scorer=PerceptionScorer(descriptor=PERCEPTION_DESCRIPTOR),
    )
    return registry
