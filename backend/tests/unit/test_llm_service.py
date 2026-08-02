"""
Unit tests for LLM Service
Tests the AIML API (OpenAI-compatible) integration and streaming functionality
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from services.llm_service import LLMService


def _reset_singleton():
    """Clear the singleton so each test builds a fresh service from env."""
    LLMService._instance = None
    LLMService._initialized = False


def _chat_completion(content: str) -> Mock:
    """Build a mock mirroring the shape of an OpenAI chat-completion response."""
    message = Mock()
    message.content = content
    choice = Mock()
    choice.message = message
    response = Mock()
    response.choices = [choice]
    return response


def _stream_chunk(content) -> Mock:
    """Build a mock mirroring one streamed chat-completion chunk."""
    delta = Mock()
    delta.content = content
    choice = Mock()
    choice.delta = delta
    chunk = Mock()
    chunk.choices = [choice]
    return chunk


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Provide AIML API configuration for testing"""
    monkeypatch.setenv("AIML_API_KEY", "test_api_key")
    monkeypatch.setenv("AIML_BASE_URL", "https://api.aimlapi.com/v1")
    monkeypatch.setenv("AIML_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("AIML_MAX_TOKENS", "2048")
    monkeypatch.setenv("AIML_TEMPERATURE", "0.7")
    _reset_singleton()
    yield
    _reset_singleton()


class TestLLMServiceConfiguration:
    """Configuration and lifecycle"""

    def test_reads_configuration_from_environment(self, mock_env_vars):
        service = LLMService()

        assert service.api_key == "test_api_key"
        assert service.base_url == "https://api.aimlapi.com/v1"
        assert service.model_id == "gpt-4o-mini"
        assert service.max_tokens == 2048
        assert service.temperature == 0.7

    def test_applies_defaults_when_optional_vars_absent(self, monkeypatch):
        monkeypatch.setenv("AIML_API_KEY", "test_api_key")
        for var in ("AIML_BASE_URL", "AIML_MODEL", "AIML_MAX_TOKENS", "AIML_TEMPERATURE"):
            monkeypatch.delenv(var, raising=False)
        _reset_singleton()

        service = LLMService()

        assert service.base_url == "https://api.aimlapi.com/v1"
        assert service.model_id == "gpt-4o-mini"
        assert service.max_tokens == 2048
        assert service.temperature == 0.7
        _reset_singleton()

    def test_singleton_pattern(self, mock_env_vars):
        assert LLMService() is LLMService()

    @patch("services.llm_service.OpenAI")
    def test_client_is_built_lazily_and_cached(self, mock_openai, mock_env_vars):
        service = LLMService()

        # Constructing the service must not touch the provider.
        mock_openai.assert_not_called()

        first, second = service.client, service.client

        mock_openai.assert_called_once_with(
            api_key="test_api_key", base_url="https://api.aimlapi.com/v1"
        )
        assert first is second

    def test_missing_api_key_does_not_raise_at_construction(self, monkeypatch):
        """A missing key must not crash import/startup — only actual use should fail."""
        monkeypatch.delenv("AIML_API_KEY", raising=False)
        _reset_singleton()

        service = LLMService()  # must not raise

        assert service.health_check()["configured"] is False
        with pytest.raises(ValueError, match="Missing AIML API credentials"):
            _ = service.client
        _reset_singleton()


class TestGenerate:
    """Synchronous generation"""

    @patch("services.llm_service.OpenAI")
    def test_generate_basic(self, mock_openai, mock_env_vars):
        client = MagicMock()
        client.chat.completions.create.return_value = _chat_completion("This is a test response")
        mock_openai.return_value = client

        response = LLMService().generate("Test prompt")

        assert response == "This is a test response"
        kwargs = client.chat.completions.create.call_args[1]
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["messages"] == [{"role": "user", "content": "Test prompt"}]
        assert kwargs["max_tokens"] == 2048
        assert kwargs["temperature"] == 0.7

    @patch("services.llm_service.OpenAI")
    def test_generate_with_system_prompt(self, mock_openai, mock_env_vars):
        client = MagicMock()
        client.chat.completions.create.return_value = _chat_completion("ok")
        mock_openai.return_value = client

        LLMService().generate("Question", system="You are a legal assistant")

        assert client.chat.completions.create.call_args[1]["messages"] == [
            {"role": "system", "content": "You are a legal assistant"},
            {"role": "user", "content": "Question"},
        ]

    @patch("services.llm_service.OpenAI")
    def test_generate_overrides_defaults(self, mock_openai, mock_env_vars):
        client = MagicMock()
        client.chat.completions.create.return_value = _chat_completion("Response")
        mock_openai.return_value = client

        LLMService().generate("Test prompt", max_tokens=100, temperature=0.5)

        kwargs = client.chat.completions.create.call_args[1]
        assert kwargs["max_tokens"] == 100
        assert kwargs["temperature"] == 0.5

    @patch("services.llm_service.OpenAI")
    def test_legacy_max_new_tokens_alias_is_translated(self, mock_openai, mock_env_vars):
        """Watsonx-era callers passed max_new_tokens; it must map to max_tokens."""
        client = MagicMock()
        client.chat.completions.create.return_value = _chat_completion("Response")
        mock_openai.return_value = client

        LLMService().generate("Test prompt", max_new_tokens=321)

        kwargs = client.chat.completions.create.call_args[1]
        assert kwargs["max_tokens"] == 321
        assert "max_new_tokens" not in kwargs

    @patch("services.llm_service.OpenAI")
    def test_unsupported_kwargs_are_dropped(self, mock_openai, mock_env_vars):
        """An unknown kwarg must not be forwarded and turned into a provider 400."""
        client = MagicMock()
        client.chat.completions.create.return_value = _chat_completion("Response")
        mock_openai.return_value = client

        LLMService().generate("Test prompt", decoding_method="greedy")

        assert "decoding_method" not in client.chat.completions.create.call_args[1]

    @patch("services.llm_service.OpenAI")
    def test_none_content_returns_empty_string(self, mock_openai, mock_env_vars):
        client = MagicMock()
        client.chat.completions.create.return_value = _chat_completion(None)
        mock_openai.return_value = client

        assert LLMService().generate("Test prompt") == ""

    @patch("services.llm_service.OpenAI")
    def test_generate_error_handling(self, mock_openai, mock_env_vars):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = client

        with pytest.raises(Exception, match="LLM generation error"):
            LLMService().generate("Test prompt")


class TestGenerateStream:
    """Streaming generation"""

    @staticmethod
    def _async_stream(chunks):
        async def _stream():
            for chunk in chunks:
                yield chunk
        return _stream()

    @pytest.mark.asyncio
    @patch("services.llm_service.AsyncOpenAI")
    async def test_generate_stream(self, mock_async_openai, mock_env_vars):
        chunks = [_stream_chunk(c) for c in ["Hello", " ", "world", "!"]]
        client = MagicMock()

        async def create(**kwargs):
            return self._async_stream(chunks)

        client.chat.completions.create = create
        mock_async_openai.return_value = client

        tokens = [t async for t in LLMService().generate_stream("Test prompt")]

        assert tokens == ["Hello", " ", "world", "!"]

    @pytest.mark.asyncio
    @patch("services.llm_service.AsyncOpenAI")
    async def test_stream_skips_empty_deltas(self, mock_async_openai, mock_env_vars):
        """Role-only/keepalive chunks carry a None delta and must be skipped."""
        chunks = [_stream_chunk(None), _stream_chunk("real"), _stream_chunk("")]
        client = MagicMock()

        async def create(**kwargs):
            return self._async_stream(chunks)

        client.chat.completions.create = create
        mock_async_openai.return_value = client

        tokens = [t async for t in LLMService().generate_stream("Test prompt")]

        assert tokens == ["real"]

    @pytest.mark.asyncio
    @patch("services.llm_service.AsyncOpenAI")
    async def test_stream_requests_streaming_mode(self, mock_async_openai, mock_env_vars):
        captured = {}
        client = MagicMock()

        async def create(**kwargs):
            captured.update(kwargs)
            return self._async_stream([_stream_chunk("x")])

        client.chat.completions.create = create
        mock_async_openai.return_value = client

        [t async for t in LLMService().generate_stream("Test prompt")]

        assert captured["stream"] is True
        assert captured["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    @patch("services.llm_service.AsyncOpenAI")
    async def test_generate_stream_error_handling(self, mock_async_openai, mock_env_vars):
        client = MagicMock()

        async def create(**kwargs):
            raise Exception("Streaming error")

        client.chat.completions.create = create
        mock_async_openai.return_value = client

        with pytest.raises(Exception, match="LLM streaming error"):
            async for _ in LLMService().generate_stream("Test prompt"):
                pass


class TestModelInfo:
    """Introspection helpers used by health/info endpoints"""

    def test_get_model_info(self, mock_env_vars):
        info = LLMService().get_model_info()

        assert info["model_id"] == "gpt-4o-mini"
        assert info["max_tokens"] == 2048
        assert info["temperature"] == 0.7
        assert info["url"] == "https://api.aimlapi.com/v1"
        assert info["provider"] == "AIML API"

    def test_health_check_reports_configured(self, mock_env_vars):
        health = LLMService().health_check()

        assert health["configured"] is True
        assert health["provider"] == "AIML API"
        assert health["model"] == "gpt-4o-mini"


class TestGlobalLLMService:
    """The module-level singleton other modules import"""

    def test_global_instance_exists(self):
        from services.llm_service import llm_service

        assert llm_service is not None
        assert isinstance(llm_service, LLMService)
