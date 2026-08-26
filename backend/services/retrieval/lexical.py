"""
BM25 over the corpus, fused with dense retrieval.

The two retrievers fail on **disjoint sets**, which is the only thing that
makes fusing them worth the complexity. Measured over the golden set, each
alone, recall@3 (dense with the structured filter off, so the comparison is
retriever against retriever):

    class            BM25    dense
    citation        0.875    0.250
    judgement       1.000    0.833
    plain           1.000    0.960
    repealed_code   0.375    0.375
    term_of_art     0.250    0.875

BM25 is better everywhere except ``term_of_art``, where it is catastrophic, and
both failures have the same single cause read from opposite ends: *whether the
words of the query appear in the text of the answer*.

* A **citation** is almost pure lexical signal. "482" is a token BM25 matches
  exactly, while a dense embedder puts "482" and "483" at nearly the same point
  -- the finding that ``structured_filter`` exists for.
* A **term of art** is the reverse: "anticipatory" occurs nowhere in BNSS 482,
  so there is no token to match and BM25 cannot reach it at any depth. This is
  the claim this project used to make about BM25 in general ("a hybrid would
  not fix this class of miss"), and it is right about *that class* and wrong as
  a reason not to have BM25 at all -- it says nothing about the classes where
  the query's own words are the answer's words.

Fusion is **Reciprocal Rank Fusion**, not a weighted score sum. BM25 scores are
unbounded and corpus-dependent while cosine distances sit in a fixed range, so
any weighted sum needs a normalisation that is itself a tuned parameter fitted
to 69 queries. RRF reads only the *ranks*, so there is nothing to normalise and
nothing to overfit:

    score(d) = sum over retrievers of 1 / (K + rank(d))

``K`` damps the top of each list so a single retriever's rank-1 cannot win on
its own -- an agreement between two retrievers at rank 3 outranks one
retriever's rank 1. That is the property being bought: a document both
retrievers like is more likely to be right than one either loves alone.

The index is built in memory from the chroma collection at first use. At 3,184
chunks that is a few megabytes and under a second, so it needs no persistence
layer and cannot fall out of sync with the vector store -- it is built from the
same rows.
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# Okapi BM25's usual defaults. Not tuned: 69 golden queries is far too few to
# fit two parameters without fitting the queries instead of the corpus.
K1 = float(os.getenv("BM25_K1", "1.5"))
B = float(os.getenv("BM25_B", "0.75"))

# RRF damping. 60 is the value from the paper the method comes from, and it is
# left there for the same reason K1 and B are: tuning it on this golden set
# would be fitting the set.
RRF_K = int(os.getenv("RRF_K", "60"))

# How deep each retriever goes before fusion. Deeper than the reranker's pool,
# because fusion is what decides which candidates the cross-encoder ever sees.
CANDIDATES = int(os.getenv("HYBRID_CANDIDATES", "30"))

_TOKEN = re.compile(r"[a-z0-9]+")


def hybrid_enabled() -> bool:
    """Whether lexical retrieval is fused in for calls that do not say."""
    return os.getenv("ENABLE_HYBRID", "true").strip().lower() in {"1", "true", "yes"}


def tokenise(text: str) -> list[str]:
    """
    Lowercase alphanumeric runs.

    Deliberately not stemmed and not stopworded. Stemming would collapse
    "bailable" and "bail", which the First Schedule and the BNSS use to mean
    different things, and a stopword list would drop the "of" in "abuse of the
    process of the Court" -- a phrase that is doing real work in BNSS 528.
    Section numbers survive as their own tokens, which is where most of BM25's
    advantage on the citation class comes from.
    """
    return _TOKEN.findall(text.lower())


class BM25Index:
    """An Okapi BM25 index over one collection, held in memory."""

    def __init__(self, documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        # The text is kept as well as the statistics: a chunk BM25 finds that
        # dense retrieval missed has to arrive at the prompt with its text, and
        # re-fetching it from chroma one id at a time would undo the point of
        # holding the index in memory.
        self.documents = documents
        self.metadatas = metadatas
        corpus = [tokenise(doc) for doc in documents]
        self.n = len(corpus)
        self.lengths = [len(doc) for doc in corpus]
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 0.0
        self.frequencies = [Counter(doc) for doc in corpus]

        document_frequency: Counter[str] = Counter()
        for doc in corpus:
            document_frequency.update(set(doc))
        # The BM25+ form of the idf, which cannot go negative. The textbook
        # form does for a term in more than half the documents, and "court"
        # is in more than half of sc_judgements -- a negative idf there would
        # score a judgement *down* for mentioning a court.
        self.idf = {
            term: math.log(1 + (self.n - count + 0.5) / (count + 0.5))
            for term, count in document_frequency.items()
        }

    def top(self, query: str, k: int) -> list[int]:
        """Indices of the k best-scoring documents, best first."""
        terms = tokenise(query)
        if not terms or not self.n:
            return []

        scored: list[tuple[float, int]] = []
        for index in range(self.n):
            frequencies = self.frequencies[index]
            length = self.lengths[index]
            score = 0.0
            for term in terms:
                frequency = frequencies.get(term)
                if not frequency:
                    continue
                score += self.idf.get(term, 0.0) * (
                    frequency
                    * (K1 + 1)
                    / (frequency + K1 * (1 - B + B * length / self.avgdl))
                )
            if score > 0:
                scored.append((score, index))

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [index for _, index in scored[:k]]


_indexes: dict[str, BM25Index] = {}
_lock = threading.Lock()


def get_index(collection: Any, name: str) -> BM25Index | None:
    """
    The BM25 index for a collection, built once per process.

    Returns ``None`` if it cannot be built. Like the reranker, lexical
    retrieval degrades to dense-only rather than failing the request: an
    unavailable index is a quality regression, an exception is an outage.
    """
    if name in _indexes:
        return _indexes[name]
    with _lock:
        if name in _indexes:
            return _indexes[name]
        try:
            data = collection.get(include=["documents", "metadatas"])
            documents = data.get("documents") or []
            if not documents:
                logger.warning(f"{name} is empty; lexical retrieval disabled for it")
                return None
            logger.info(f"building BM25 index over {len(documents)} chunks in {name}")
            _indexes[name] = BM25Index(documents, data.get("metadatas") or [])
        except Exception as error:  # pragma: no cover - environment dependent
            logger.warning(f"could not build BM25 index for {name} ({error})")
            return None
        return _indexes[name]


def reset_indexes() -> None:
    """Drop the cached indexes, for tests and after a reseed."""
    _indexes.clear()


def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = RRF_K
) -> list[str]:
    """
    Fuse ranked id lists into one, best first.

    Rank-based rather than score-based on purpose -- see the module docstring.
    A document absent from a ranking simply contributes nothing from it, so a
    retriever that fails completely on a query (BM25 on a term of art, and it
    does fail completely) drags nothing down; it just stops voting.

    Ties break towards the document that appeared earliest in the first
    ranking that contains it, so with one retriever this is the identity.
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, tuple[int, int]] = {}
    for ranking_index, ranking in enumerate(rankings):
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc_id not in first_seen:
                first_seen[doc_id] = (ranking_index, rank)
    return sorted(
        scores, key=lambda doc_id: (-scores[doc_id], first_seen[doc_id])
    )
