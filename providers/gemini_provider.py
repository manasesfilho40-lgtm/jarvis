import json
import logging
import time
import urllib.request
from typing import Any, AsyncGenerator, Generator

from providers.provider_manager import (
    BaseProvider, EmbeddingResponse, ModelConfig, ProviderResponse, ProviderType,
)

logger = logging.getLogger("gemini_provider")


class GeminiProvider(BaseProvider):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_base = config.base_url or "https://generativelanguage.googleapis.com/v1beta"

    def _build_url(self, model: str = "") -> str:
        m = model or self.config.model
        return f"{self.api_base}/models/{m}:generateContent?key={self.config.api_key}"

    def _build_stream_url(self, model: str = "") -> str:
        m = model or self.config.model
        return f"{self.api_base}/models/{m}:streamGenerateContent?key={self.config.api_key}&alt=sse"

    def _call_api(self, prompt: str, system: str = "", model: str = "", stream: bool = False) -> dict:
        url = self._build_stream_url(model) if stream else self._build_url(model)
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_output,
            },
        }
        if system:
            data["systemInstruction"] = {"parts": [{"text": system}]}

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def generate(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        start = time.time()
        try:
            result = self._call_api(prompt, system)
            text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            latency = (time.time() - start) * 1000
            tokens_in = sum(len(str(p)) for p in result.get("usageMetadata", {}).get("promptTokenCount", 0))
            tokens_out = result.get("usageMetadata", {}).get("candidatesTokenCount", 0)
            self._record_call(latency, tokens_in, tokens_out)
            return ProviderResponse(
                text=text, model=self.config.model, provider=ProviderType.GEMINI,
                latency_ms=latency,
                usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
            )
        except Exception as e:
            self._record_call((time.time() - start) * 1000, error=True)
            raise

    def generate_stream(self, prompt: str, system: str = "", **kwargs) -> Generator[str, None, None]:
        result = self._call_api(prompt, system, stream=True)
        candidates = result.get("candidates", [])
        for candidate in candidates:
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    yield part["text"]

    async def generate_async(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        return self.generate(prompt, system, **kwargs)

    async def generate_stream_async(self, prompt: str, system: str = "", **kwargs) -> AsyncGenerator[str, None]:
        for chunk in self.generate_stream(prompt, system, **kwargs):
            yield chunk


def create_gemini_provider(api_key: str = "", model: str = "gemini-2.5-flash-lite") -> GeminiProvider:
    config = ModelConfig(
        model=model,
        provider=ProviderType.GEMINI,
        api_key=api_key,
        context_length=128000,
        max_output=8192,
        supports_streaming=True,
        supports_vision=True,
        supports_tools=True,
        supports_embeddings=False,
    )
    return GeminiProvider(config)
