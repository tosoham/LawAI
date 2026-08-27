"""
The specialists a plan can dispatch to.

Each is a thin adapter over a service that already exists and is already
measured. None of them reimplements retrieval, classification or graph
traversal: the whole point of the fan-out is to ask the *same* pipeline several
questions in parallel, not to grow a second one that drifts away from what
``eval_retrieval.py`` measures.

Importing this package registers every runner. ``lookups`` and ``retrieval``
are imported for that side effect and are not re-exported.
"""
from agents.specialists import lookups, retrieval  # noqa: F401  (registration)
from agents.specialists.base import (
    MAX_RETRIEVALS,
    RetrievalBudget,
    SpecialistResult,
    run_specialist,
)

__all__ = [
    "MAX_RETRIEVALS",
    "RetrievalBudget",
    "SpecialistResult",
    "run_specialist",
]
