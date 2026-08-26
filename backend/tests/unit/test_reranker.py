"""
Cross-encoder reranking.

The model itself is not tested here -- ms-marco's judgement is the vendor's,
and pinning it would be pinning someone else's weights. What is tested is
everything around it, which is where this can go wrong quietly:

* a reranker that cannot load must leave retrieval working, because a quality
  regression is survivable and an outage is not;
* the ordering and the scores shown to the reader must come from the same
  model, or the page lists sources in one order and scores them in another;
* a cited section resolved by exact lookup must not be reorderable, since the
  cross-encoder works from the same surface signal that put citation recall@3
  at 0.250 in the first place.
"""
import math
from unittest.mock import MagicMock, patch

import pytest

from services.retrieval.reranker import (
    Reranker,
    as_distance,
    get_reranker,
    rerank_enabled,
    reset_reranker,
)
from services.vector_service import VectorService


@pytest.fixture(autouse=True)
def _clean_singleton():
    reset_reranker()
    yield
    reset_reranker()


def _model(scores):
    model = MagicMock()
    model.predict.return_value = scores
    return model


class TestScoring:
    def test_documents_are_ordered_best_first(self):
        reranker = Reranker()
        reranker._model = _model([-4.0, 9.0, 1.0])

        assert reranker.order("q", ["a", "b", "c"]) == [1, 2, 0]

    def test_a_tie_keeps_the_order_it_was_given(self):
        """
        A reranker with nothing to say must not shuffle bi-encoder ranking.
        The sort is stable and the index is the tiebreak, so equal scores come
        back in the order they arrived.
        """
        reranker = Reranker()
        reranker._model = _model([2.0, 2.0, 2.0])

        assert reranker.order("q", ["a", "b", "c"]) == [0, 1, 2]

    def test_no_documents_scores_nothing(self):
        reranker = Reranker()
        reranker._model = _model([])

        assert reranker.score("q", []) == []


class TestFailingSoft:
    def test_a_model_that_will_not_load_keeps_the_order(self):
        reranker = Reranker("no-such-model")
        with patch(
            "sentence_transformers.CrossEncoder", side_effect=OSError("not found")
        ):
            assert reranker.order("q", ["a", "b"]) is None
            assert not reranker.available

    def test_the_failure_is_not_retried_on_every_call(self):
        """Loading is attempted once. A 90 MB download that is going to fail
        should fail once per process, not once per query."""
        reranker = Reranker("no-such-model")
        with patch(
            "sentence_transformers.CrossEncoder", side_effect=OSError("not found")
        ) as constructor:
            for _ in range(3):
                reranker.order("q", ["a"])
            assert constructor.call_count == 1

    def test_a_scoring_failure_keeps_the_order(self):
        reranker = Reranker()
        model = MagicMock()
        model.predict.side_effect = RuntimeError("cuda gone")
        reranker._model = model

        assert reranker.order("q", ["a", "b"]) is None


class TestDistanceConversion:
    def test_a_high_score_is_a_near_distance(self):
        assert as_distance(9.0) < 0.01

    def test_a_low_score_is_a_far_distance(self):
        assert as_distance(-9.0) > 0.99

    def test_a_neutral_score_sits_in_the_middle(self):
        assert as_distance(0.0) == pytest.approx(0.5)

    def test_the_conversion_is_absolute_not_relative_to_the_batch(self):
        """
        Min-max over the batch would score the best of five poor candidates
        1.0. The reader would see a confident number over a bad answer, which
        is the one thing this project refuses everywhere else.
        """
        assert as_distance(-8.0) > 0.9
        assert as_distance(-7.0) > 0.9

    def test_an_extreme_score_does_not_overflow(self):
        assert 0.0 <= as_distance(-10_000.0) <= 1.0
        assert 0.0 <= as_distance(10_000.0) <= 1.0
        assert not math.isnan(as_distance(10_000.0))


class TestSearchIntegration:
    """``VectorService._rerank`` in isolation from chromadb."""

    @staticmethod
    def _results():
        return {
            "ids": ["a", "b", "c"],
            "documents": ["doc a", "doc b", "doc c"],
            "metadatas": [{"n": 1}, {"n": 2}, {"n": 3}],
            "distances": [0.10, 0.20, 0.30],
        }

    def test_every_field_is_reordered_together(self):
        reranker = Reranker()
        reranker._model = _model([-4.0, 9.0, 1.0])
        with patch(
            "services.vector_service.get_reranker", return_value=reranker
        ):
            out = VectorService._rerank("q", self._results(), top_k=3)

        assert out["ids"] == ["b", "c", "a"]
        assert out["documents"] == ["doc b", "doc c", "doc a"]
        assert out["metadatas"] == [{"n": 2}, {"n": 3}, {"n": 1}]

    def test_the_displayed_distance_comes_from_the_reranker(self):
        """
        The regression this guards. ``_format_sources`` renders ``1 -
        distance`` as a relevance score, so keeping the bi-encoder's distances
        under a cross-encoder ordering shows the reader source 2 scoring above
        source 1. The bi-encoder's numbers are kept, but beside rather than
        instead.
        """
        reranker = Reranker()
        reranker._model = _model([-4.0, 9.0, 1.0])
        with patch(
            "services.vector_service.get_reranker", return_value=reranker
        ):
            out = VectorService._rerank("q", self._results(), top_k=3)

        assert out["distances"] == sorted(out["distances"])
        assert out["vector_distances"] == [0.20, 0.30, 0.10]

    def test_the_list_is_cut_to_top_k(self):
        reranker = Reranker()
        reranker._model = _model([-4.0, 9.0, 1.0])
        with patch(
            "services.vector_service.get_reranker", return_value=reranker
        ):
            out = VectorService._rerank("q", self._results(), top_k=2)

        assert out["ids"] == ["b", "c"]

    def test_an_unavailable_reranker_truncates_without_reordering(self):
        reranker = Reranker("no-such-model")
        reranker._unavailable = True
        with patch(
            "services.vector_service.get_reranker", return_value=reranker
        ):
            out = VectorService._rerank("q", self._results(), top_k=2)

        assert out["ids"] == ["a", "b"]
        assert out["distances"] == [0.10, 0.20]

    def test_no_results_are_left_alone(self):
        empty = {"ids": [], "documents": [], "metadatas": [], "distances": []}
        out = VectorService._rerank("q", empty, top_k=5)
        assert out == empty


class TestExactHitsOutrankTheReranker:
    def test_a_cited_section_stays_first_after_reranking(self):
        """
        The ordering constraint that makes this safe to enable. A section
        resolved by exact metadata lookup is merged *after* reranking, so the
        cross-encoder cannot demote it -- it scores from the same surface
        signal that made "section 482 BNSS" miss BNSS 482 in the top 20.
        """
        exact = {
            "ids": ["bnss_482"],
            "documents": ["482. ..."],
            "metadatas": [{"section_number": "482"}],
            "distances": [0.0],
        }
        reranked = {
            "ids": ["x", "y"],
            "documents": ["doc x", "doc y"],
            "metadatas": [{"n": 1}, {"n": 2}],
            "distances": [0.01, 0.02],
        }

        merged = VectorService._merge_exact_hits(exact, reranked, top_k=3)

        assert merged["ids"][0] == "bnss_482"
        assert merged["ids"] == ["bnss_482", "x", "y"]


class TestEnableFlag:
    def test_on_by_default(self, monkeypatch):
        """On because it was measured: +0.043 recall@3 overall, no class down,
        recall@1 0.812 -> 0.870 with recall@10 unmoved."""
        monkeypatch.delenv("ENABLE_RERANK", raising=False)
        assert rerank_enabled() is True

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
    def test_recognised_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("ENABLE_RERANK", value)
        assert rerank_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "maybe"])
    def test_anything_not_truthy_is_off(self, monkeypatch, value):
        monkeypatch.setenv("ENABLE_RERANK", value)
        assert rerank_enabled() is False

    def test_the_singleton_is_reused(self):
        assert get_reranker() is get_reranker()
