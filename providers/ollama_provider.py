import json
import logging
import time
import urllib.request
from typing import Any, AsyncGenerator, Generator

from providers.provider_manager import (
    BaseProvider, EmbeddingResponse, ModelConfig, ProviderResponse, ProviderType,
)

logger = logging.getLogger("ollama_provider")


class OllamaProvider(BaseProvider):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_base = config.base_url or "http://127.0.0.1:11434"

    def _call_api(self, prompt: str, system: str = "", model: str = "", stream: bool = False) -> dict:
        m = model or self.config.model
        data = {
            "model": m,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_output,
            },
        }
        if system:
            data["system"] = system

        url = f"{self.api_base}/api/generate"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(f"{self.api_base}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
            return []

    def generate(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        start = time.time()
        try:
            result = self._call_api(prompt, system)
            text = result.get("response", "").strip()
            latency = (time.time() - start) * 1000
            eval_count = result.get("eval_count", 0)
            prompt_eval = result.get("prompt_eval_count", 0)
            self._record_call(latency, prompt_eval, eval_count)
            return ProviderResponse(
                text=text, model=self.config.model, provider=ProviderType.OLLAMA,
                latency_ms=latency,
                usage={"prompt_tokens": prompt_eval, "completion_tokens": eval_count},
            )
        except Exception as e:
            self._record_call((time.time() - start) * 1000, error=True)
            raise

    def generate_stream(self, prompt: str, system: str = "", **kwargs) -> Generator[str, None, None]:
        m = kwargs.get("model", self.config.model)
        data = {"model": m, "prompt": prompt, "stream": True}
        if system:
            data["system"] = system

        url = f"{self.api_base}/api/generate"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                if line.strip():
                    chunk = json.loads(line.decode("utf-8"))
                    if "response" in chunk:
                        yield chunk["response"]

    async def generate_async(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        return self.generate(prompt, system, **kwargs)

    async def generate_stream_async(self, prompt: str, system: str = "", **kwargs) -> AsyncGenerator[str, None]:
        for chunk in self.generate_stream(prompt, system, **kwargs):
            yield chunk

    def embed(self, texts: list[str]) -> EmbeddingResponse:
        start = time.time()
        embeddings = []
        total_tokens = 0
        for text in texts:
            data = {"model": self.config.model, "prompt": text}
            url = f"{self.api_base}/api/embeddings"
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embeddings.append(result.get("embedding", []))
                total_tokens += result.get("prompt_eval_count", 0)

        latency = (time.time() - start) * 1000
        return EmbeddingResponse(
            embeddings=embeddings, model=self.config.model,
            provider=ProviderType.OLLAMA, latency_ms=latency,
            usage={"prompt_tokens": total_tokens},
        )


def create_ollama_provider(model: str = "qwen2.5:7b", base_url: str = "") -> OllamaProvider:
    config = ModelConfig(
        model=model,
        provider=ProviderType.OLLAMA,
        base_url=base_url or "http://127.0.0.1:11434",
        context_length=32768,
        max_output=4096,
        supports_streaming=True,
        supports_vision=False,
        supports_tools=False,
        supports_embeddings=True,
    )
    return OllamaProvider(config)
