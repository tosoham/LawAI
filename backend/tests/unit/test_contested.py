"""
Two advocates, one rebuttal, no winner.

The only place in this system where more than one agent does something one
agent cannot. Everywhere else fan-out buys latency; here a single agent is
structurally unable to do the job, because developing a reading while
simultaneously arguing against it produces the hedged middle that reads as
balance and is neither position stated properly.

Three properties are load-bearing and each has a way of failing quietly:

* **independence before rebuttal** -- if an advocate sees the other's argument
  while writing its own, it anchors, and the two positions converge into one;
* **neither may concede** -- convergence produces a single position, which
  `claim_verifier` rejects for carrying fewer than two, so a "successful"
  debate becomes an abstention;
* **an unsupported position is reported, not dropped** -- that a side cannot be
  supported from this corpus is a finding, and a better one than a fabricated
  citation propping it up.
"""
import json
from unittest.mock import MagicMock

import pytest

from agents.contested import REBUTTAL_ROUNDS, develop_positions


def replying(*payloads):
    service = MagicMock()
    service.generate.side_effect = [
        p if isinstance(p, str) else json.dumps(p) for p in payloads
    ]
    return service


def both_sides(**overrides):
    first = {
        "label": "Bail is the rule",
        "summary": "Liberty is the norm and detention the exception.",
        "authority": ["BNSS 480", "sc_state_of_rajasthan_jaipur_v_balchand_1977"],
    }
    second = {
        "label": "The statutory bar is strict",
        "summary": "The twin conditions must be satisfied before bail.",
        "authority": ["BNSS 480"],
    }
    first.update(overrides.get("first", {}))
    second.update(overrides.get("second", {}))
    return first, second


SIDES = ("bail is the rule", "the statutory bar is strict")


class TestTheExchange:
    def test_both_positions_are_developed_then_each_answers_the_other(self):
        first, second = both_sides()
        service = replying(
            first, second, {"rebuttal": "Their reading ignores the proviso."},
            {"rebuttal": "Liberty does not displace a statutory bar."},
        )

        positions, errors = develop_positions("q", SIDES, "material", service)

        assert len(positions) == 2
        assert all(p.rebuttal for p in positions)
        assert errors == []

    def test_it_costs_exactly_four_model_calls(self):
        """Two positions and two rebuttals. Bounded, and the bound is the
        point: open dialogue converges, and convergence here is a failure."""
        first, second = both_sides()
        service = replying(first, second, {"rebuttal": "a"}, {"rebuttal": "b"})

        develop_positions("q", SIDES, "material", service)

        assert service.generate.call_count == 2 + 2 * REBUTTAL_ROUNDS

    def test_neither_advocate_sees_the_other_while_writing_its_own(self):
        """
        Independence first, or they anchor and converge. Checked by looking at
        what was actually in each of the first two prompts.
        """
        first, second = both_sides()
        service = replying(first, second, {"rebuttal": "a"}, {"rebuttal": "b"})

        develop_positions("q", SIDES, "material", service)

        opening_prompts = [
            call.kwargs["prompt"] for call in service.generate.call_args_list[:2]
        ]
        assert first["summary"] not in opening_prompts[1]
        assert second["summary"] not in opening_prompts[0]

    def test_the_rebuttal_prompt_carries_the_other_side(self):
        first, second = both_sides()
        service = replying(first, second, {"rebuttal": "a"}, {"rebuttal": "b"})

        develop_positions("q", SIDES, "material", service)

        rebuttal_prompt = service.generate.call_args_list[2].kwargs["prompt"]
        assert second["summary"] in rebuttal_prompt


class TestNeitherMayConcedeOrInvent:
    def test_a_position_with_no_authority_is_reported_not_dropped(self):
        """That a side cannot be supported from this corpus is a finding."""
        first, second = both_sides(first={"authority": []})
        service = replying(first, second, {"rebuttal": "a"}, {"rebuttal": "b"})

        positions, _ = develop_positions("q", SIDES, "material", service)

        assert len(positions) == 2
        assert not positions[0].supported
        assert positions[1].supported

    def test_the_prompt_forbids_conceding(self):
        from agents.contested import ADVOCATE_SYSTEM

        assert "may not concede" in ADVOCATE_SYSTEM.lower()

    def test_the_prompt_forbids_inventing_authority(self):
        from agents.contested import ADVOCATE_SYSTEM

        assert "may not invent" in ADVOCATE_SYSTEM.lower()

    def test_the_prompt_says_citations_are_checked(self):
        """An advocate told its citations are checked has a reason not to
        stretch one, and it is true — the verifier checks every claim."""
        from agents.contested import ADVOCATE_SYSTEM

        assert "checked" in ADVOCATE_SYSTEM.lower()

    def test_a_label_is_a_name_not_a_verdict(self):
        import re

        from agents.contested import ADVOCATE_INSTRUCTIONS

        flattened = re.sub(r"\s+", " ", ADVOCATE_INSTRUCTIONS).lower()
        assert "not whether it wins" in flattened


class TestDegrading:
    def test_one_advocate_failing_leaves_the_other(self):
        """
        Honest rather than complete. One position is a one-sided answer with a
        warning on it, and the verifier refuses to render it as contested —
        correctly.
        """
        _, second = both_sides()
        service = MagicMock()
        service.generate.side_effect = [RuntimeError("down"), json.dumps(second)]

        positions, errors = develop_positions("q", SIDES, "material", service)

        assert len(positions) == 1
        assert len(errors) == 1

    def test_no_rebuttal_round_runs_when_only_one_side_stands(self):
        _, second = both_sides()
        service = MagicMock()
        service.generate.side_effect = [RuntimeError("down"), json.dumps(second)]

        develop_positions("q", SIDES, "material", service)

        assert service.generate.call_count == 2, "no rebuttal without an opponent"

    @pytest.mark.parametrize("raw", ["not json", "{}", json.dumps({"summary": ""})])
    def test_an_unusable_reply_is_an_error_not_a_crash(self, raw):
        _, second = both_sides()
        service = replying(raw, second)

        positions, errors = develop_positions("q", SIDES, "material", service)

        assert len(positions) == 1
        assert errors and "no usable position" in errors[0].message

    def test_a_failing_rebuttal_keeps_the_positions(self):
        first, second = both_sides()
        service = MagicMock()
        service.generate.side_effect = [
            json.dumps(first),
            json.dumps(second),
            RuntimeError("down"),
            RuntimeError("down"),
        ]

        positions, _ = develop_positions("q", SIDES, "material", service)

        assert len(positions) == 2
        assert all(p.summary for p in positions)
        assert all(p.rebuttal == "" for p in positions)

    def test_both_failing_yields_nothing_rather_than_raising(self):
        service = MagicMock()
        service.generate.side_effect = RuntimeError("down")

        positions, errors = develop_positions("q", SIDES, "material", service)

        assert positions == []
        assert len(errors) == 2


class TestSideSelection:
    def test_the_sides_come_from_the_curated_doctrine(self):
        """
        `doctrines.json` records where authority splits and names both sides
        without declaring a winner — exactly the input this needs, and exactly
        what a model should not be asked to invent.
        """
        from unittest.mock import MagicMock as M

        from agents.intent_classifier import IntentClassifier
        from agents.legal_agent import LegalAgent

        agent = LegalAgent(IntentClassifier(), M(), llm_service=M())
        sides = agent._contested_sides({"user_query": "is the law on BNSS 480 settled"})

        assert "twin conditions" in sides[0].lower()
        assert sides[0] != sides[1]

    def test_a_question_with_no_curated_doctrine_still_gets_two_sides(self):
        """A question can be genuinely open without this repository having
        catalogued it."""
        from unittest.mock import MagicMock as M

        from agents.intent_classifier import IntentClassifier
        from agents.legal_agent import LegalAgent

        agent = LegalAgent(IntentClassifier(), M(), llm_service=M())
        sides = agent._contested_sides({"user_query": "is this unconstitutional"})

        assert len(sides) == 2
        assert sides[0] != sides[1]
