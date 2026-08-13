"""
Unit tests for the procedural timeline and the offences endpoint.

The timeline tells someone how long they can be held. Getting the branch wrong
-- sixty days when it is ninety, or ninety when it is sixty -- is the kind of
confident wrong answer that does real harm, so most of these are about the
branch: that it follows the statute's own threshold, and that it refuses to
pick when the punishment cannot be read.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from services.legal_graph import get_legal_graph
from services.procedural_timeline import (
    LONG_CUSTODY_DAYS,
    SHORT_CUSTODY_DAYS,
    build_timeline,
    classify_punishment,
    for_section,
)


class TestClassifyPunishment:
    @pytest.mark.parametrize(
        "punishment,death_or_life,years",
        [
            ("Death or imprisonment for life and fine.", True, None),
            ("Imprisonment for life, or imprisonment for 10 years.", True, None),
            ("Imprisonment for 7 years and fine.", False, 7),
            ("Imprisonment for 10 years and fine.", False, 10),
            ("Imprisonment for 2 years, or fine, or both.", False, 2),
            (
                "Imprisonment for not less than 7 years but which may extend to 14 years",
                False,
                14,
            ),
        ],
    )
    def test_the_thresholds_the_statute_uses(self, punishment, death_or_life, years):
        severity = classify_punishment(punishment)
        assert severity.death_or_life is death_or_life
        assert severity.max_years == years
        assert severity.resolved

    def test_the_gazette_hyphenation_does_not_hide_a_life_sentence(self):
        """The Schedule carries the PDF's line-break hyphens into its own
        punishment column: "imprison- ment for life"."""
        assert classify_punishment("One half of the imprison- ment for life").death_or_life

    @pytest.mark.parametrize(
        "punishment",
        ["Same as for offence abetted.", "Fine only.", "", "   ", "Community service."],
    )
    def test_a_punishment_it_cannot_read_is_reported_unresolved(self, punishment):
        """Giving up is a result. The caller says the limit depends on the
        underlying offence rather than inventing one."""
        severity = classify_punishment(punishment)
        assert not severity.resolved
        assert severity.custody_limit_days is None

    def test_the_boundary_is_ten_years(self):
        assert classify_punishment("9 years").custody_limit_days == SHORT_CUSTODY_DAYS
        assert classify_punishment("10 years").custody_limit_days == LONG_CUSTODY_DAYS


class TestBuildTimeline:
    def timeline(self, punishment, cognizable=True):
        return build_timeline(classify_punishment(punishment), cognizable, get_legal_graph())

    def test_every_step_cites_a_section(self):
        for step in self.timeline("7 years").steps:
            assert step.section.startswith("BNSS ")
            assert step.section_title

    def test_the_sections_are_the_ones_that_govern_custody(self):
        sections = {s.section for s in self.timeline("7 years").steps}
        assert sections == {"BNSS 35", "BNSS 57", "BNSS 58", "BNSS 187", "BNSS 193", "BNSS 479"}

    def test_a_life_sentence_gets_ninety_days_and_says_why(self):
        timeline = self.timeline("Death or imprisonment for life")
        assert timeline.custody_limit_days == LONG_CUSTODY_DAYS
        assert "187(3)(i)" in timeline.limit_basis

    def test_a_lesser_offence_gets_sixty(self):
        timeline = self.timeline("Imprisonment for 3 years")
        assert timeline.custody_limit_days == SHORT_CUSTODY_DAYS
        assert "187(3)(ii)" in timeline.limit_basis

    def test_an_unreadable_punishment_refuses_to_pick(self):
        timeline = self.timeline("Same as for offence abetted.")
        assert timeline.custody_limit_days is None
        assert "could not be determined" in timeline.limit_basis
        step = next(s for s in timeline.steps if "release on bail" in s.stage)
        assert step.conditional
        assert "60 or 90" in step.stage

    def test_undertrial_release_is_withheld_where_the_statute_withholds_it(self):
        """BNSS 479 excludes offences punishable with death or life
        imprisonment, so showing it there would be simply wrong."""
        assert not any(s.section == "BNSS 479" for s in self.timeline("Death").steps)
        assert any(s.section == "BNSS 479" for s in self.timeline("3 years").steps)

    def test_a_non_cognizable_offence_marks_warrantless_arrest_conditional(self):
        """Marked, not dropped: the step still belongs in the sequence."""
        step = self.timeline("3 years", cognizable=False).steps[0]
        assert step.section == "BNSS 35"
        assert step.conditional

    def test_an_unresolved_cognizability_is_also_conditional(self):
        assert self.timeline("3 years", cognizable=None).steps[0].conditional


class TestForSection:
    def test_an_offence_carries_its_classification_and_timeline(self):
        payload = for_section("BNS", "103")
        assert payload["title"] == "Punishment for murder"
        assert len(payload["classification"]) == 2
        assert payload["timeline"]["custody_limit_days"] == LONG_CUSTODY_DAYS

    def test_the_graph_material_comes_along(self):
        payload = for_section("BNS", "103")
        assert [d["name"] for d in payload["doctrines"]] == ["Rarest of rare"]
        assert len(payload["judgements"]) == 3

    def test_a_procedural_section_has_no_classification_rather_than_a_wrong_one(self):
        """All of the BNSS is procedure. An empty card is honest; a fabricated
        one is not."""
        payload = for_section("BNSS", "187")
        assert payload["title"]
        assert payload["classification"] == []
        assert payload["timeline"] is None

    def test_the_most_serious_row_drives_the_timeline(self):
        """
        BNS 303 classifies theft and petty theft separately. The exposure a
        person actually faces is the more serious one, so that is what the
        timeline is built from.
        """
        assert for_section("BNS", "303")["timeline"]["custody_limit_days"] == SHORT_CUSTODY_DAYS

    def test_a_section_that_does_not_exist(self):
        assert for_section("BNS", "999") is None


class TestEndpoint:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_a_known_offence(self, client):
        response = client.get("/api/v1/offences/BNS/103")
        assert response.status_code == 200
        assert response.json()["timeline"]["custody_limit_days"] == 90

    def test_the_act_is_case_insensitive(self, client):
        assert client.get("/api/v1/offences/bns/103").status_code == 200

    def test_an_unknown_act(self, client):
        response = client.get("/api/v1/offences/IPC/302")
        assert response.status_code == 404
        assert "BNS" in response.json()["detail"]

    def test_an_unknown_section(self, client):
        assert client.get("/api/v1/offences/BNS/999").status_code == 404

    def test_the_summary_publishes_what_it_cannot_resolve(self, client):
        """A client showing a classification UI needs to know that "not
        stated" is a real outcome for about forty rows."""
        summary = client.get("/api/v1/offences").json()
        assert summary["classified_sections"] == 288
        assert summary["unresolved_cognizable"] > 0
        assert summary["unresolved_bailable"] > 0

    def test_a_deliberate_404_keeps_its_message(self, client):
        """
        The app-wide 404 handler replaced every body with "The requested
        resource was not found", throwing away the answer: "BNS has no section
        999" is what the caller asked for, not an error string.
        """
        body = client.get("/api/v1/offences/BNS/999").json()
        assert "no section 999" in body["message"]

    def test_a_wrong_url_still_gets_the_generic_message(self, client):
        body = client.get("/api/v1/nothing-here").json()
        assert body["message"] == "The requested resource was not found"
