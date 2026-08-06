"""
Unit tests for the retrieval eval harness.

The scoring functions are the measuring instrument for every later retrieval
change. A wrong metric would make regressions look like improvements, so these
pin the arithmetic rather than trusting it.
"""
import json
from pathlib import Path

import pytest

from tests.unit.test_ingestion import _load_script

eval_retrieval = _load_script("eval_retrieval")

PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden_queries.json"


class TestDedupe:
    """A long section occupies several chunks; ranking must be over parents."""

    def test_repeated_keys_collapse_keeping_first_position(self):
        assert eval_retrieval.dedupe(["480", "480", "482", "480", "483"]) == [
            "480",
            "482",
            "483",
        ]

    def test_none_keys_are_dropped(self):
        """A chunk missing its metadata key must not occupy a rank."""
        assert eval_retrieval.dedupe(["103", None, "104"]) == ["103", "104"]

    def test_empty(self):
        assert eval_retrieval.dedupe([]) == []


class TestScoreQuery:
    def test_hit_at_rank_one(self):
        score = eval_retrieval.score_query(["482", "480"], ["482"])
        assert score["first_rank"] == 1
        assert score["rr"] == 1.0
        assert score["recall"]["@1"] is True

    def test_reciprocal_rank_uses_the_first_hit(self):
        score = eval_retrieval.score_query(["480", "483", "482"], ["482"])
        assert score["first_rank"] == 3
        assert score["rr"] == pytest.approx(1 / 3)

    def test_recall_thresholds_are_exclusive_of_later_ranks(self):
        score = eval_retrieval.score_query(["a", "b", "c", "d", "482"], ["482"])
        assert score["recall"]["@1"] is False
        assert score["recall"]["@3"] is False
        assert score["recall"]["@5"] is True
        assert score["recall"]["@10"] is True

    def test_complete_miss_scores_zero_not_none(self):
        score = eval_retrieval.score_query(["480", "483"], ["482"])
        assert score["first_rank"] is None
        assert score["rr"] == 0.0
        assert score["ndcg@10"] == 0.0
        assert not any(score["recall"].values())

    def test_ndcg_rewards_finding_more_of_the_expected_set(self):
        """Two expected sections found must outscore one."""
        both = eval_retrieval.score_query(["187", "479"], ["187", "479"])
        one = eval_retrieval.score_query(["187", "999"], ["187", "479"])
        assert both["ndcg@10"] == pytest.approx(1.0)
        assert one["ndcg@10"] < both["ndcg@10"]

    def test_ndcg_rewards_higher_placement(self):
        high = eval_retrieval.score_query(["482", "x", "y"], ["482"])
        low = eval_retrieval.score_query(["x", "y", "482"], ["482"])
        assert high["ndcg@10"] > low["ndcg@10"]

    def test_hits_past_ten_do_not_count_towards_ndcg(self):
        ranked = [f"x{i}" for i in range(10)] + ["482"]
        score = eval_retrieval.score_query(ranked, ["482"])
        assert score["ndcg@10"] == 0.0
        assert score["first_rank"] == 11


class TestAggregate:
    def test_empty_input_is_reported_rather_than_averaged(self):
        assert eval_retrieval.aggregate([]) == {"n": 0}

    def test_means_across_queries(self):
        rows = [
            {"score": eval_retrieval.score_query(["a"], ["a"])},
            {"score": eval_retrieval.score_query(["b"], ["a"])},
        ]
        summary = eval_retrieval.aggregate(rows)
        assert summary["n"] == 2
        assert summary["recall@1"] == 0.5
        assert summary["mrr"] == 0.5


class TestGoldenSet:
    """
    The fixture is only as good as its expectations.

    A golden entry pointing at a section that does not exist would silently
    become an unreachable target, making every future run look worse than it is.
    """

    @pytest.fixture(scope="class")
    def golden(self):
        return json.loads(GOLDEN_PATH.read_text())

    @pytest.fixture(scope="class")
    def corpus_ids(self):
        ids = {}
        for collection, filename in [
            ("bns_sections", "bns_sections.json"),
            ("bnss_sections", "bnss_sections.json"),
            ("bsa_sections", "bsa_sections.json"),
        ]:
            records = json.loads((PROCESSED_DIR / filename).read_text())
            ids[collection] = {r["metadata"]["section_number"] for r in records}
        judgements = json.loads((PROCESSED_DIR / "sc_judgements.json").read_text())
        ids["sc_judgements"] = {r["id"] for r in judgements}
        return ids

    def test_every_expected_id_exists_in_the_corpus(self, golden, corpus_ids):
        missing = [
            (q["id"], q["collection"], expected)
            for q in golden["queries"]
            for expected in q["expected"]
            if expected not in corpus_ids[q["collection"]]
        ]
        assert not missing, f"golden set references non-existent ids: {missing}"

    def test_query_ids_are_unique(self, golden):
        ids = [q["id"] for q in golden["queries"]]
        assert len(ids) == len(set(ids))

    def test_every_class_is_populated(self, golden):
        classes = {q["class"] for q in golden["queries"]}
        assert classes == {
            "plain",
            "term_of_art",
            "citation",
            "repealed_code",
            "judgement",
        }

    def test_adversarial_set_has_no_expected_answers(self, golden):
        """
        These exist to test abstention. Giving them expected ids would turn a
        correct "I don't know" into a scored failure.
        """
        for query in golden["adversarial"]["queries"]:
            assert "expected" not in query
            assert query["why"]
