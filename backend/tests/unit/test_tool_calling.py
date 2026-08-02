"""
Unit tests for LLM function calling and the live case-law tools.

The provider is mocked throughout: what matters here is that the tool-calling
loop feeds results back correctly, terminates, and reports what it invoked.
"""
from unittest.mock import MagicMock, patch

import pytest

from services.llm_service import MAX_TOOL_ROUNDS, LLMService
from tools.live_case_law_tool import (
    FetchJudgmentTool,
    LiveCaseLawSearchTool,
    build_openai_tool_schemas,
)


def _reset_singleton():
    LLMService._instance = None
    LLMService._initialized = False


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("AIML_API_KEY", "test_key")
    monkeypatch.setenv("AIML_MODEL", "gpt-4o-mini")
    _reset_singleton()
    yield
    _reset_singleton()


def _tool_call(call_id: str, name: str, arguments: str) -> MagicMock:
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = arguments
    return call


def _response(content=None, tool_calls=None) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestGenerateWithTools:
    @patch("services.llm_service.OpenAI")
    def test_returns_directly_when_no_tool_is_needed(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.return_value = _response(content="Settled law answer")
        mock_openai.return_value = client
        executor = MagicMock()

        result = LLMService().generate_with_tools("q", tools=[], executor=executor)

        assert result["content"] == "Settled law answer"
        assert result["tool_calls"] == []
        executor.assert_not_called()

    @patch("services.llm_service.OpenAI")
    def test_executes_a_tool_and_feeds_the_result_back(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _response(tool_calls=[
                _tool_call("c1", "live_case_law_search", '{"query": "bail", "limit": 3}')
            ]),
            _response(content="Two 2026 judgments found"),
        ]
        mock_openai.return_value = client
        executor = MagicMock(return_value={"success": True, "data": {"results": []}})

        result = LLMService().generate_with_tools("recent bail rulings", tools=[], executor=executor)

        executor.assert_called_once_with("live_case_law_search", {"query": "bail", "limit": 3})
        assert result["content"] == "Two 2026 judgments found"
        assert result["tool_calls"][0]["name"] == "live_case_law_search"
        assert result["rounds"] == 1

        # The tool reply must reference the call that produced it.
        messages = client.chat.completions.create.call_args_list[1][1]["messages"]
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["tool_call_id"] == "c1"
        assert messages[-2]["role"] == "assistant"

    @patch("services.llm_service.OpenAI")
    def test_handles_several_calls_in_one_round(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _response(tool_calls=[
                _tool_call("c1", "search_local_corpus", '{"query": "BNS 111"}'),
                _tool_call("c2", "live_case_law_search", '{"query": "organised crime"}'),
            ]),
            _response(content="Combined answer"),
        ]
        mock_openai.return_value = client
        executor = MagicMock(return_value={"success": True})

        result = LLMService().generate_with_tools("q", tools=[], executor=executor)

        assert executor.call_count == 2
        assert [c["name"] for c in result["tool_calls"]] == [
            "search_local_corpus", "live_case_law_search"
        ]

    @patch("services.llm_service.OpenAI")
    def test_a_failing_tool_is_reported_to_the_model_not_raised(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _response(tool_calls=[_tool_call("c1", "live_case_law_search", "{}")]),
            _response(content="The live source was unavailable, so from the corpus..."),
        ]
        mock_openai.return_value = client
        executor = MagicMock(side_effect=RuntimeError("source down"))

        result = LLMService().generate_with_tools("q", tools=[], executor=executor)

        assert "unavailable" in result["content"]
        assert result["tool_calls"][0]["result"]["success"] is False
        assert "source down" in result["tool_calls"][0]["result"]["error"]

    @patch("services.llm_service.OpenAI")
    def test_malformed_arguments_do_not_crash_the_loop(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _response(tool_calls=[_tool_call("c1", "live_case_law_search", "not json")]),
            _response(content="ok"),
        ]
        mock_openai.return_value = client
        executor = MagicMock(return_value={"success": True})

        LLMService().generate_with_tools("q", tools=[], executor=executor)

        executor.assert_called_once_with("live_case_law_search", {})

    @patch("services.llm_service.OpenAI")
    def test_loop_terminates_when_the_model_keeps_asking_for_tools(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.return_value = _response(
            tool_calls=[_tool_call("c1", "live_case_law_search", "{}")]
        )
        mock_openai.return_value = client

        result = LLMService().generate_with_tools(
            "q", tools=[], executor=MagicMock(return_value={"success": True})
        )

        assert result["rounds"] == MAX_TOOL_ROUNDS
        # One call per round plus a final toolless call to force an answer.
        assert client.chat.completions.create.call_count == MAX_TOOL_ROUNDS + 1
        assert "tools" not in client.chat.completions.create.call_args_list[-1][1]

    @patch("services.llm_service.OpenAI")
    def test_provider_errors_surface_clearly(self, mock_openai, env):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("429 rate limited")
        mock_openai.return_value = client

        with pytest.raises(Exception, match="LLM tool-calling error"):
            LLMService().generate_with_tools("q", tools=[], executor=MagicMock())


class TestToolSchemas:
    def test_schemas_are_well_formed(self):
        schemas = build_openai_tool_schemas()
        names = {s["function"]["name"] for s in schemas}

        assert names == {"live_case_law_search", "fetch_judgment", "search_local_corpus"}
        for schema in schemas:
            assert schema["type"] == "function"
            function = schema["function"]
            assert function["description"]
            assert function["parameters"]["type"] == "object"
            for required in function["parameters"]["required"]:
                assert required in function["parameters"]["properties"]

    def test_descriptions_tell_the_model_when_to_go_live(self):
        by_name = {s["function"]["name"]: s["function"]["description"]
                   for s in build_openai_tool_schemas()}
        assert "recent" in by_name["live_case_law_search"].lower()
        assert "verified" in by_name["search_local_corpus"].lower()


class TestLiveCaseLawTools:
    @pytest.mark.asyncio
    async def test_search_tool_returns_service_payload(self):
        service = MagicMock()
        service.search_case_law.return_value = {
            "success": True, "num_results": 1,
            "results": [{"doc_id": "1", "title": "A vs B"}],
        }

        result = await LiveCaseLawSearchTool(service).execute(query="bail", limit=3)

        assert result.success is True
        assert result.data["num_results"] == 1
        assert result.metadata["live"] is True
        service.search_case_law.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_tool_requires_a_query(self):
        result = await LiveCaseLawSearchTool(MagicMock()).execute()
        assert result.success is False
        assert "query" in result.error

    @pytest.mark.asyncio
    async def test_search_tool_propagates_service_failure(self):
        service = MagicMock()
        service.search_case_law.return_value = {"success": False, "error": "source down"}

        result = await LiveCaseLawSearchTool(service).execute(query="bail")

        assert result.success is False
        assert result.error == "source down"

    @pytest.mark.asyncio
    async def test_fetch_tool_returns_judgement(self):
        service = MagicMock()
        service.fetch_judgment.return_value = {"success": True, "doc_id": "1", "text": "held..."}

        result = await FetchJudgmentTool(service).execute(doc_id="1")

        assert result.success is True
        assert result.data["text"] == "held..."
        assert result.metadata["doc_id"] == "1"

    @pytest.mark.asyncio
    async def test_fetch_tool_requires_doc_id(self):
        result = await FetchJudgmentTool(MagicMock()).execute()
        assert result.success is False
        assert "doc_id" in result.error

    def test_tools_declare_their_parameters(self):
        for tool in (LiveCaseLawSearchTool(MagicMock()), FetchJudgmentTool(MagicMock())):
            metadata = tool.get_metadata()
            assert metadata.name and metadata.description
            assert metadata.parameters
