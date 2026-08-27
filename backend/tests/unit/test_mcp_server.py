"""
LawAI over MCP.

The design constraint this file exists to pin: **grounding travels with the
tools.** An MCP client that receives retrieved text instead of checked claims
has routed around the only property that makes this system safe — the model on
the other end will turn a paragraph into a confident sentence about someone's
liberty, and it will do so outside the verifier.

So there is deliberately no raw-retrieval tool, and `ask` returns claims,
verdicts and the abstention rather than chunks. That absence is the most
important thing here, and an absence is exactly what gets added back by someone
who does not know why it is missing.
"""
import asyncio
import inspect

import pytest

import mcp_server


def tool_names():
    return {tool.name for tool in asyncio.run(mcp_server.server.list_tools())}


class TestGroundingTravelsWithTheTools:
    def test_there_is_no_raw_retrieval_tool(self):
        """
        The most convenient tool to add here, and the most dangerous. Raw
        chunks over MCP put generation outside the verifier.
        """
        assert not {"search_corpus", "search", "retrieve"} & tool_names()

    def test_ask_returns_claims_rather_than_text(self):
        source = inspect.getsource(mcp_server.ask)
        assert "epistemic_class" in source
        assert "structured.claims" in source

    def test_ask_reports_what_was_removed(self):
        """
        An answer that dropped what it could not support looks identical to one
        that never overreached, and a caller deciding how far to trust this
        needs the difference.
        """
        source = inspect.getsource(mcp_server.ask)
        assert '"removed"' in source

    def test_the_instructions_tell_a_client_the_codes_are_the_2023_ones(self):
        assert "2023" in mcp_server.INSTRUCTIONS
        assert "repealed" in mcp_server.INSTRUCTIONS.lower()

    def test_the_instructions_ask_a_client_to_preserve_the_claim_types(self):
        """The epistemic class is the point of the whole pipeline. A client
        that flattens it back into prose undoes it at the last step."""
        lowered = mcp_server.INSTRUCTIONS.lower()
        assert "epistemic class" in lowered
        assert "do not describe a case as holding" in lowered


class TestDeterministicTools:
    def test_a_section_comes_back_whole(self):
        result = mcp_server.get_section("BNS", "103")
        assert result["found"]
        assert result["citation"] == "BNS 103"
        assert "murder" in result["title"].lower()
        assert result["text"]

    def test_a_section_that_does_not_exist_says_how_far_the_act_runs(self):
        result = mcp_server.get_section("BNS", "999")
        assert not result["found"]
        assert "358" in result["error"]

    def test_classification_comes_from_the_first_schedule(self):
        result = mcp_server.classify_offence("BNS", "103")
        assert result["found"]
        assert any(
            "non-bailable" in row["bailable_text"].lower()
            for row in result["classification"]
        )

    def test_a_contested_doctrine_says_so_and_names_both_sides(self):
        """
        `doctrines.json` carries no precedential status. Where authority splits
        it says so and names both without declaring a winner, and that has to
        survive the trip through the protocol.
        """
        result = mcp_server.explain_doctrine("BNSS", "480")
        assert result["contested"]
        contested = [d for d in result["doctrines"] if d["contested"]]
        assert contested and contested[0]["contest_note"]


class TestRepealedLookup:
    def test_a_mapped_section_resolves(self):
        result = mcp_server.what_replaced("IPC", "302")
        assert result["found"]
        assert result["replaced_by"] == ["BNS 103"]

    def test_the_source_is_named(self):
        """This is the one dataset asserted by a third party rather than parsed
        from enacted text, so it says whose assertion it is."""
        assert "Bureau of Police Research" in mcp_server.what_replaced("IPC", "302")["source"]

    def test_a_bad_number_is_distinguished_from_a_bad_act(self):
        """
        "IPC 9999" reported as "IPC is not a repealed code" is a confusing
        answer to a reasonable question: the act was fine, the number was not.
        """
        assert "not a section number" in mcp_server.what_replaced("IPC", "9999")["error"]
        assert "not one of the repealed codes" in (
            mcp_server.what_replaced("Income Tax Act", "10")["error"]
        )


class TestSurface:
    def test_every_tool_carries_a_description(self):
        """A client chooses tools by description. One without is one that gets
        called for the wrong thing."""
        tools = asyncio.run(mcp_server.server.list_tools())
        assert tools
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    @pytest.mark.parametrize(
        "name",
        [
            "ask",
            "get_section",
            "classify_offence",
            "explain_doctrine",
            "what_replaced",
            "search_case_law",
            "fetch_judgment",
            "corpus_info",
        ],
    )
    def test_the_expected_tools_are_registered(self, name):
        assert name in tool_names()

    def test_live_tools_are_described_as_unverified(self):
        """
        Live results are retrieved, not curated. Nothing downstream checks
        them, so the description is the only place a client is told.
        """
        tools = {t.name: t.description for t in asyncio.run(mcp_server.server.list_tools())}
        description = tools["search_case_law"].lower()
        assert "not curated" in description
        assert "none has been verified" in description
        assert "not present one as settled law" in description

    def test_corpus_info_reports_counts_rather_than_describing_them(self):
        info = mcp_server.corpus_info()
        assert info["sections"] > 1000
        assert info["judgements"] == 300
        assert "out of scope" in info["scope"]

    def test_document_types_come_from_the_api_rather_than_a_third_list(self):
        """
        The frontend once carried its own menu and offered "Affidavit" while
        the API rejected it. A third list here would be the same bug with one
        more place to drift.
        """
        source = inspect.getsource(mcp_server.list_document_types)
        assert "from api.v1.documents import get_document_templates" in source

        result = asyncio.run(mcp_server.list_document_types())
        assert [t["type"] for t in result["templates"]]


class TestStdioSafety:
    def test_logging_goes_to_stderr(self):
        """
        stdio transport speaks JSON-RPC on stdout. A log line written there
        corrupts the stream, and the client sees a protocol error rather than a
        log.
        """
        source = inspect.getsource(mcp_server)
        assert "stream=sys.stderr" in source
