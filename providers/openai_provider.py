import base64
import json
import logging
import time
from typing import Any, AsyncGenerator, Generator

from providers.provider_manager import (
    BaseProvider, EmbeddingResponse, ModelConfig, ProviderResponse, ProviderType,
    ToolCall, ToolDefinition,
)

logger = logging.getLogger("openai_provider")


class OpenAIProvider(BaseProvider):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_base = config.base_url or "https://api.openai.com/v1"
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.api_base,
            )
            return self._client
        except ImportError:
            raise RuntimeError("openai package not installed")

    def generate(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        start = time.time()
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_output),
            )
            latency = (time.time() - start) * 1000
            choice = response.choices[0]
            text = choice.message.content or ""
            usage = response.usage
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
            self._record_call(latency, tokens_in, tokens_out)
            return ProviderResponse(
                text=text, model=self.config.model, provider=ProviderType.OPENAI,
                latency_ms=latency,
                usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
                finish_reason=choice.finish_reason or "",
            )
        except Exception as e:
            self._record_call((time.time() - start) * 1000, error=True)
            raise

    def generate_stream(self, prompt: str, system: str = "", **kwargs) -> Generator[str, None, None]:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_output),
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def generate_async(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        start = time.time()
        try:
            import openai
            async_client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.api_base,
            )
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = await async_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_output),
            )
            latency = (time.time() - start) * 1000
            text = response.choices[0].message.content or ""
            usage = response.usage
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
            self._record_call(latency, tokens_in, tokens_out)
            return ProviderResponse(
                text=text, model=self.config.model, provider=ProviderType.OPENAI,
                latency_ms=latency,
                usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
            )
        except Exception as e:
            self._record_call((time.time() - start) * 1000, error=True)
            raise

    async def generate_stream_async(self, prompt: str, system: str = "", **kwargs) -> AsyncGenerator[str, None]:
        try:
            import openai
            async_client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.api_base,
            )
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            stream = await async_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_output),
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception:
            raise

    def tools(self, prompt: str, tools: list[ToolDefinition], system: str = "", **kwargs) -> tuple[str, list[ToolCall]]:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            })

        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=openai_tools if openai_tools else None,
            temperature=kwargs.get("temperature", 0.1),
        )

        choice = response.choices[0]
        text = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                    id=tc.id,
                ))
        return text, tool_calls

    def embed(self, texts: list[str], **kwargs) -> EmbeddingResponse:
        start = time.time()
        client = self._get_client()
        embed_model = kwargs.get("model", "text-embedding-3-small")
        response = client.embeddings.create(model=embed_model, input=texts)
        embeddings = [d.embedding for d in response.data]
        latency = (time.time() - start) * 1000
        return EmbeddingResponse(
            embeddings=embeddings, model=embed_model,
            provider=ProviderType.OPENAI, latency_ms=latency,
            usage={"prompt_tokens": response.usage.total_tokens if response.usage else 0},
        )

    def vision(self, image: str | bytes, prompt: str = "", **kwargs) -> ProviderResponse:
        client = self._get_client()
        if isinstance(image, bytes):
            encoded = base64.b64encode(image).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{encoded}"
        else:
            image_url = image

        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "Describe this image"},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }],
            max_tokens=kwargs.get("max_tokens", 1024),
        )
        text = response.choices[0].message.content or ""
        return ProviderResponse(
            text=text, model=self.config.model, provider=ProviderType.OPENAI,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )


def create_openai_provider(api_key: str = "", model: str = "gpt-4o", base_url: str = "") -> OpenAIProvider:
    config = ModelConfig(
        model=model,
        provider=ProviderType.OPENAI,
        api_key=api_key,
        base_url=base_url,
        context_length=128000,
        max_output=8192,
        supports_streaming=True,
        supports_vision="vision" in model or "gpt-4o" in model,
        supports_tools=True,
        supports_embeddings=True,
    )
    return OpenAIProvider(config)


def create_openrouter_provider(api_key: str = "", model: str = "openai/gpt-4o", base_url: str = "https://openrouter.ai/api/v1") -> OpenAIProvider:
    config = ModelConfig(
        model=model,
        provider=ProviderType.OPENROUTER,
        api_key=api_key,
        base_url=base_url,
        context_length=128000,
        max_output=8192,
        supports_streaming=True,
        supports_vision=True,
        supports_tools=True,
        supports_embeddings=False,
    )
    return OpenAIProvider(config)
