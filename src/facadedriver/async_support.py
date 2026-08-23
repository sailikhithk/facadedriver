"""Async support for FacadeDriver.

Provides AsyncBackend protocol, AsyncMockBackend, and an async
generate() method on FacadeDriver. The async path uses asyncio
for concurrency and httpx for HTTP when talking to provider SDKs
that support async clients.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol, runtime_checkable

from facadedriver.types import BackendResponse, Message


@runtime_checkable
class AsyncBackend(Protocol):
    async def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse: ...


class AsyncMockBackend:
    """Async version of MockBackend for tests and demos."""

    def __init__(
        self,
        *,
        content: str | None = None,
        latency_ms: float = 50.0,
        fail_models: set[str] | None = None,
        provider: str = "mock",
    ) -> None:
        self._content = content
        self._latency_ms = latency_ms
        self._fail_models = fail_models or set()
        self._provider = provider
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse:
        self.calls.append({"model": model, "messages": messages, "kwargs": kwargs})
        if model in self._fail_models:
            raise RuntimeError(f"AsyncMockBackend forced failure for model '{model}'")
        await asyncio.sleep(self._latency_ms / 1000.0)
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        content = self._content if self._content is not None else f"[async-mock:{model}] {last_user}"
        return BackendResponse(
            content=content,
            model=model,
            provider=self._provider,
            input_tokens=sum(len(m.get("content", "").split()) for m in messages),
            output_tokens=len(content.split()),
            cost_usd=0.0,
            latency_ms=self._latency_ms,
            raw={"mock": True, "async": True},
        )


class AsyncRawSDKBackend:
    """Async backend using provider SDKs' async clients.

    Uses openai.AsyncOpenAI, anthropic.AsyncAnthropic, and
    google.genai (which is async-native). Install the relevant SDK
    to use the corresponding provider.
    """

    def __init__(self, providers: dict[str, Any] | None = None) -> None:
        self._providers = providers or {}

    def _provider_for(self, model: str) -> str:
        if model.startswith("gpt-") or model.startswith("openai/"):
            return "openai"
        if model.startswith("claude-"):
            return "anthropic"
        if model.startswith("gemini-"):
            return "google"
        raise ValueError(f"Unknown provider for model '{model}'")

    async def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse:
        provider = self._provider_for(model)
        start = time.perf_counter()
        if provider == "openai":
            resp = await self._call_openai(model, messages, temperature, max_tokens, kwargs)
        elif provider == "anthropic":
            resp = await self._call_anthropic(model, messages, temperature, max_tokens, kwargs)
        else:
            resp = await self._call_google(model, messages, temperature, max_tokens, kwargs)
        latency = (time.perf_counter() - start) * 1000
        resp.provider = provider
        resp.latency_ms = latency
        return resp

    async def _call_openai(self, model, messages, temperature, max_tokens, kwargs):
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as e:
            raise ImportError("openai SDK not installed. Run `pip install openai`.") from e
        client = self._providers.get("openai") or AsyncOpenAI()
        resp = await client.chat.completions.create(
            model=model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, **kwargs,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return BackendResponse(
            content=choice.message.content or "", model=model, provider="openai",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    async def _call_anthropic(self, model, messages, temperature, max_tokens, kwargs):
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise ImportError("anthropic SDK not installed. Run `pip install anthropic`.") from e
        client = self._providers.get("anthropic") or anthropic.AsyncAnthropic()
        system = next((m["content"] for m in messages if m.get("role") == "system"), None)
        user_messages = [m for m in messages if m.get("role") != "system"]
        resp = await client.messages.create(
            model=model, messages=user_messages,
            system=system or anthropic.NOT_GIVEN,
            temperature=temperature, max_tokens=max_tokens or 1024, **kwargs,
        )
        content = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return BackendResponse(
            content=content, model=model, provider="anthropic",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    async def _call_google(self, model, messages, temperature, max_tokens, kwargs):
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise ImportError("google-genai SDK not installed. Run `pip install google-genai`.") from e
        client = self._providers.get("google") or genai.Client()
        contents = [
            genai.types.Content(role=m["role"], parts=[genai.types.Part(text=m["content"])])
            for m in messages
        ]
        config = genai.types.GenerateContentConfig(
            temperature=temperature, max_output_tokens=max_tokens,
        )
        resp = await client.aio.models.generate_content(
            model=model, contents=contents, config=config,
        )
        text = resp.text or ""
        usage = resp.usage_metadata
        return BackendResponse(
            content=text, model=model, provider="google",
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
        )
