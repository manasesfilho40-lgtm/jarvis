import base64
import json
import logging
import time
from typing import Any, AsyncGenerator, Generator

from providers.provider_manager import (
    BaseProvider, EmbeddingResponse, ModelConfig, ProviderResponse, ProviderType,
    ToolCall, ToolDefinition,
)

logger = logging.getLogger("anthropic_provider")


class AnthropicProvider(BaseProvider):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_base = config.base_url or "https://api.anthropic.com/v1"
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.config.api_key)
            return self._client
        except ImportError:
            raise RuntimeError("anthropic package not installed")

    def generate(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        start = time.time()
        client = self._get_client()
        try:
            message = client.messages.create(
                model=self.config.model,
                max_tokens=kwargs.get("max_tokens", self.config.max_output),
                system=system or None,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.config.temperature),
            )
            latency = (time.time() - start) * 1000
            text = "".join(block.text for block in message.content if block.type == "text") if message.content else ""
            tokens_in = message.usage.input_tokens if message.usage else 0
            tokens_out = message.usage.output_tokens if message.usage else 0
            self._record_call(latency, tokens_in, tokens_out)
            return ProviderResponse(
                text=text, model=self.config.model, provider=ProviderType.ANTHROPIC,
                latency_ms=latency,
                usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
                finish_reason=message.stop_reason or "",
            )
        except Exception as e:
            self._record_call((time.time() - start) * 1000, error=True)
            raise

    def generate_stream(self, prompt: str, system: str = "", **kwargs) -> Generator[str, None, None]:
        client = self._get_client()
        with client.messages.stream(
            model=self.config.model,
            max_tokens=kwargs.get("max_tokens", self.config.max_output),
            system=system or None,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", self.config.temperature),
        ) as stream:
            for text in stream.text_stream:
                yield text

    async def generate_async(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        start = time.time()
        try:
            from anthropic import AsyncAnthropic
            async_client = AsyncAnthropic(api_key=self.config.api_key)
            message = await async_client.messages.create(
                model=self.config.model,
                max_tokens=kwargs.get("max_tokens", self.config.max_output),
                system=system or None,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.config.temperature),
            )
            latency = (time.time() - start) * 1000
            text = "".join(block.text for block in message.content if block.type == "text") if message.content else ""
            tokens_in = message.usage.input_tokens if message.usage else 0
            tokens_out = message.usage.output_tokens if message.usage else 0
            self._record_call(latency, tokens_in, tokens_out)
            return ProviderResponse(
                text=text, model=self.config.model, provider=ProviderType.ANTHROPIC,
                latency_ms=latency,
                usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
            )
        except Exception as e:
            self._record_call((time.time() - start) * 1000, error=True)
            raise

    async def generate_stream_async(self, prompt: str, system: str = "", **kwargs) -> AsyncGenerator[str, None]:
        try:
            from anthropic import AsyncAnthropic
            async_client = AsyncAnthropic(api_key=self.config.api_key)
            async with async_client.messages.stream(
                model=self.config.model,
                max_tokens=kwargs.get("max_tokens", self.config.max_output),
                system=system or None,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.config.temperature),
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception:
            raise

    def tools(self, prompt: str, tools: list[ToolDefinition], system: str = "", **kwargs) -> tuple[str, list[ToolCall]]:
        client = self._get_client()
        anthropic_tools = []
        for t in tools:
            anthropic_tools.append({
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            })

        message = client.messages.create(
            model=self.config.model,
            max_tokens=kwargs.get("max_tokens", self.config.max_output),
            system=system or None,
            messages=[{"role": "user", "content": prompt}],
            tools=anthropic_tools or None,
            temperature=kwargs.get("temperature", 0.1),
        )

        text = ""
        tool_calls = []
        if message.content:
            for block in message.content:
                if block.type == "text":
                    text += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                        id=block.id,
                    ))
        return text, tool_calls

    def vision(self, image: str | bytes, prompt: str = "", **kwargs) -> ProviderResponse:
        client = self._get_client()
        if isinstance(image, bytes):
            encoded = base64.b64encode(image).decode("utf-8")
            media_type = kwargs.get("media_type", "image/jpeg")
        else:
            media_type = "image/jpeg"
            encoded = image

        message = client.messages.create(
            model=self.config.model,
            max_tokens=kwargs.get("max_tokens", 1024),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "Describe this image"},
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded}},
                ],
            }],
        )
        text = "".join(block.text for block in message.content if block.type == "text") if message.content else ""
        return ProviderResponse(
            text=text, model=self.config.model, provider=ProviderType.ANTHROPIC,
            usage={"prompt_tokens": message.usage.input_tokens if message.usage else 0,
                   "completion_tokens": message.usage.output_tokens if message.usage else 0},
        )


def create_anthropic_provider(api_key: str = "", model: str = "claude-3-5-sonnet-20241022") -> AnthropicProvider:
    config = ModelConfig(
        model=model,
        provider=ProviderType.ANTHROPIC,
        api_key=api_key,
        context_length=200000,
        max_output=8192,
        supports_streaming=True,
        supports_vision=True,
        supports_tools=True,
        supports_embeddings=False,
    )
    return AnthropicProvider(config)
