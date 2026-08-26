"""
Rescore retrieved chunks with a cross-encoder.

The bi-encoder that builds the index embeds the query and the chunk
*separately* and compares two points. That is what makes an index searchable at
all -- every chunk is embedded once, offline -- and it is also its ceiling: the
model never sees the query and the chunk together, so it cannot notice that a
chunk answers this particular question rather than merely inhabiting the same
region of law. A cross-encoder does see them together, scores one pair at a
time, and is therefore far too slow to run over a corpus and exactly right for
reordering twenty candidates.

**Measured before building it.** ``backend/eval/`` records recall@1 0.8116
against recall@10 0.9855: in roughly one query in five the right chunk is
retrieved and ranked below first. That is the gap a reranker closes, and the
same numbers say what would *not* help -- with recall@10 at 0.9855 there is
almost nothing left to recall, so adding a lexical retriever alongside the
dense one would be work spent on the 1.5% rather than the 19%.

**It is scored on the expanded query, not the user's wording**, and that was
not the first guess. Reranking was built on the raw query on the reasoning that
expansion is a crutch for a bi-encoder which never sees the chunk, while a
cross-encoder does. Measured, that cost ``term_of_art`` 0.250 of recall@3 and
0.306 of MRR and made the whole change a net loss. The reason is the same one
``services.query_expansion`` exists for: a term of art is often absent from the
section that governs it, so a cross-encoder shown "grounds for anticipatory
bail" reads a chunk of BNSS 482 that never says "anticipatory" and demotes what
expansion had just surfaced. Seeing both texts together does not tell a model
they are the same thing. The alias table is what says so.

Three things this deliberately does not touch:

* **A cited section stays pinned.** ``VectorService.search`` reranks the vector
  hits and merges the exact lookup on top afterwards. Reranking a structured
  hit would be a category error: it was resolved by an exact metadata key, and
  the cross-encoder scores from the same surface signal that made citation
  retrieval the worst class in the baseline at recall@3 0.250. A model that
  cannot tell 482 from 483 must not be allowed to overrule a lookup that can.
* **The index is unchanged.** Reranking is a read-path reordering, so it needs
  no reindex and can be turned off per call.
* **Recall.** A reranker reorders what was retrieved; it can only move the
  answer up or down within the candidate pool, never add one. If the pool is
  too shallow it will confidently promote the best of a bad set, which is why
  the candidate depth is a knob and is measured rather than assumed.

It fails soft. A reranker that cannot load returns the input order and logs
once: retrieval degrading to bi-encoder ranking is a quality regression, while
retrieval raising is an outage, and the second is much worse.
"""
from __future__ import annotations

import logging
import math
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# ms-marco-MiniLM-L-6-v2: ~90 MB, CPU-friendly, and trained for exactly this
# job (reordering passages retrieved for a query). Overridable so a better one
# can be swapped in behind the eval rather than argued about.
DEFAULT_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# How many candidates to pull from the vector store before reordering. 20 is
# where recall@k flattens on the golden set -- deeper costs cross-encoder
# inference on chunks that were never going to win.
DEFAULT_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "20"))

# The chunker targets ~1200 characters, so 512 tokens holds a whole chunk with
# room for the query. Truncation here would silently score a chunk on its first
# half.
MAX_LENGTH = int(os.getenv("RERANK_MAX_LENGTH", "512"))


def rerank_enabled() -> bool:
    """
    Whether reranking is on by default for calls that do not say.

    On, because it was measured against ``eval/concordance.json`` and beat it
    on every class or held level:

        class            R@3      MRR
        citation      +0.000   +0.000     (pinned by the exact lookup)
        judgement     +0.083   +0.044
        plain         +0.040   +0.063
        repealed_code +0.000   +0.000     (pinned)
        term_of_art   +0.062   +0.040
        OVERALL       +0.043   +0.040

    recall@1 goes 0.812 -> 0.870 while recall@10 stays at 0.986, which is the
    shape a reranker is supposed to have: the same answers, further up. Set
    ``ENABLE_RERANK=false`` to measure without it or to run somewhere the model
    cannot be fetched.
    """
    return os.getenv("ENABLE_RERANK", "true").strip().lower() in {"1", "true", "yes"}


class Reranker:
    """Lazily-loaded cross-encoder, safe to hold as a process-wide singleton."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: Any = None
        self._unavailable = False
        # The model is built on first use from several threads at once (the
        # eval harness runs a pool, and so does uvicorn). Without the lock they
        # each build their own copy of a 90 MB model.
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is not None or self._unavailable:
            return self._model
        with self._lock:
            if self._model is not None or self._unavailable:
                return self._model
            try:
                from sentence_transformers import CrossEncoder

                logger.info(f"loading cross-encoder {self.model_name}")
                self._model = CrossEncoder(self.model_name, max_length=MAX_LENGTH)
            except Exception as error:  # pragma: no cover - environment dependent
                # Logged once, at warning rather than error: the caller has a
                # working answer without us.
                self._unavailable = True
                logger.warning(
                    f"cross-encoder {self.model_name} unavailable ({error}); "
                    "falling back to bi-encoder ranking"
                )
            return self._model

    @property
    def available(self) -> bool:
        return self._load() is not None

    def score(self, query: str, documents: list[str]) -> list[float] | None:
        """
        Relevance of each document to the query, higher is better.

        ``None`` when the model could not be loaded, which the caller must read
        as "keep the order you had" rather than as "these are all irrelevant".
        """
        if not documents:
            return []
        model = self._load()
        if model is None:
            return None
        try:
            scores = model.predict([(query, doc) for doc in documents])
        except Exception as error:  # pragma: no cover - environment dependent
            logger.warning(f"cross-encoder scoring failed ({error}); keeping order")
            return None
        return [float(score) for score in scores]

    def order(self, query: str, documents: list[str]) -> list[int] | None:
        """
        Indices of ``documents`` best-first, or ``None`` to keep the order.

        Ties keep their original position: ``sorted`` is stable and the index is
        the tiebreak, so a reranker with nothing to say leaves bi-encoder
        ranking intact instead of shuffling it.
        """
        scores = self.score(query, documents)
        if scores is None:
            return None
        return sorted(range(len(documents)), key=lambda i: (-scores[i], i))


_reranker: Reranker | None = None
_reranker_lock = threading.Lock()


def get_reranker() -> Reranker:
    """The process-wide reranker."""
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                _reranker = Reranker()
    return _reranker


def reset_reranker() -> None:
    """Drop the singleton, for tests."""
    global _reranker
    _reranker = None


def as_distance(score: float) -> float:
    """
    A cross-encoder score as a chroma-style distance, lower being nearer.

    Everything downstream reads ``distances`` and computes ``1 - distance`` as a
    relevance score -- ``RAGService._format_sources`` does, and the UI renders
    it. Leaving the bi-encoder's distances in place under a reranked ordering
    would show the reader a list ordered one way and scored another, with the
    second source scoring above the first. The raw distances are preserved
    separately under ``vector_distances`` so the eval can still see them.

    A logistic squash rather than a min-max over the batch: min-max would make
    the best of five poor candidates score 1.0, which is exactly the
    overclaiming this project refuses everywhere else. The logistic is absolute
    -- ms-marco scores are logits, so 0 maps to 0.5 and the large negative
    scores an irrelevant chunk earns stay near zero.
    """
    return 1.0 - 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, score))))
