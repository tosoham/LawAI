"""
AIML API LLM Service

Singleton service wrapping the AIML API (https://aimlapi.com), which exposes an
OpenAI-compatible chat-completions endpoint. Accessed via the official ``openai``
SDK pointed at AIML's ``base_url``.

The client is constructed lazily so that a missing/invalid API key does not crash
the application at import time — health endpoints stay reachable and the error
surfaces only when generation is actually attempted.
"""
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.aimlapi.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.7

# Generation kwargs callers are allowed to override per-request. Anything else is
# dropped rather than forwarded, so an unexpected kwarg can't turn into a 400 from
# the provider.
_ALLOWED_GEN_KWARGS = {"max_tokens", "temperature", "top_p", "stop", "presence_penalty",
                       "frequency_penalty", "seed"}

# Back-compat: the watsonx era used ``max_new_tokens``. Map it rather than break callers.
_KWARG_ALIASES = {"max_new_tokens": "max_tokens"}


class LLMService:
    """Singleton service for AIML API LLM operations."""

    _instance: Optional['LLMService'] = None
    _initialized: bool = False

    def __new__(cls):
        """Ensure singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Read configuration from the environment (clients are created lazily)."""
        if self._initialized:
            return

        self.api_key = os.getenv("AIML_API_KEY")
        self.base_url = os.getenv("AIML_BASE_URL", DEFAULT_BASE_URL)
        self.model_id = os.getenv("AIML_MODEL", DEFAULT_MODEL)
        self.max_tokens = int(os.getenv("AIML_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
        self.temperature = float(os.getenv("AIML_TEMPERATURE", str(DEFAULT_TEMPERATURE)))

        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None
        self._initialized = True

        if not self.api_key:
            logger.warning(
                "AIML_API_KEY is not set. LLM calls will fail until it is configured in .env"
            )
        else:
            logger.info(f"LLM Service configured with model: {self.model_id}")

    def _require_api_key(self) -> str:
        """Return the API key or raise a clear configuration error."""
        if not self.api_key:
            raise ValueError(
                "Missing AIML API credentials. Set AIML_API_KEY in backend/.env "
                "(get a key from https://aimlapi.com)."
            )
        return self.api_key

    @property
    def client(self) -> OpenAI:
        """Lazily-constructed synchronous client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._require_api_key(), base_url=self.base_url)
        return self._client

    @property
    def async_client(self) -> AsyncOpenAI:
        """Lazily-constructed asynchronous client (used for real token streaming)."""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self._require_api_key(), base_url=self.base_url
            )
        return self._async_client

    def _build_params(self, **kwargs) -> dict[str, Any]:
        """
        Merge per-call overrides over the configured defaults.

        Unknown kwargs are dropped; ``max_new_tokens`` is accepted as a legacy alias
        for ``max_tokens``.
        """
        for legacy, current in _KWARG_ALIASES.items():
            if legacy in kwargs:
                kwargs[current] = kwargs.pop(legacy)

        params: dict[str, Any] = {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        params.update({k: v for k, v in kwargs.items() if k in _ALLOWED_GEN_KWARGS})
        return params

    @staticmethod
    def _build_messages(prompt: str, system: str | None = None) -> list:
        """Wrap a raw prompt string into the chat-completions message format."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(self, prompt: str, system: str | None = None, **kwargs) -> str:
        """
        Generate a completion for a prompt.

        Args:
            prompt: Input prompt text
            system: Optional system message
            **kwargs: Generation overrides (max_tokens, temperature, ...)

        Returns:
            Generated text response

        Raises:
            Exception: If generation fails
        """
        try:
            logger.debug(f"Generating completion for prompt: {prompt[:100]}...")

            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=self._build_messages(prompt, system),
                **self._build_params(**kwargs),
            )

            content = response.choices[0].message.content or ""
            logger.debug(f"Generated response: {content[:100]}...")
            return content

        except Exception as e:
            logger.error(f"Generation failed: {e!s}")
            raise Exception(f"LLM generation error: {e!s}") from e

    async def generate_stream(
        self, prompt: str, system: str | None = None, **kwargs
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion, yielding tokens as they arrive.

        Args:
            prompt: Input prompt text
            system: Optional system message
            **kwargs: Generation overrides (max_tokens, temperature, ...)

        Yields:
            Token strings as they are generated

        Raises:
            Exception: If streaming fails
        """
        try:
            logger.debug(f"Starting streaming generation for prompt: {prompt[:100]}...")

            stream = await self.async_client.chat.completions.create(
                model=self.model_id,
                messages=self._build_messages(prompt, system),
                stream=True,
                **self._build_params(**kwargs),
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                token = chunk.choices[0].delta.content
                if token:
                    yield token

        except Exception as e:
            logger.error(f"Streaming generation failed: {e!s}")
            raise Exception(f"LLM streaming error: {e!s}") from e

    def get_model_info(self) -> dict:
        """
        Get information about the current model.

        Returns:
            Dictionary with model configuration
        """
        return {
            "model_id": self.model_id,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "url": self.base_url,
            "provider": "AIML API",
        }

    def health_check(self) -> dict:
        """
        Report whether the service is configured well enough to serve requests.

        Does not call the provider — this stays cheap enough for health endpoints.
        """
        return {
            "configured": bool(self.api_key),
            "model": self.model_id,
            "provider": "AIML API",
            "base_url": self.base_url,
        }


# Global singleton instance
llm_service = LLMService()
