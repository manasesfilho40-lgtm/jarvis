import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Generator, Optional

logger = logging.getLogger("provider_manager")


class ProviderType(Enum):
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    CUSTOM = "custom"


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)


@dataclass
class ModelConfig:
    model: str
    provider: ProviderType
    base_url: str = ""
    api_key: str = ""
    context_length: int = 4096
    max_output: int = 2048
    temperature: float = 0.7
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_tools: bool = False
    supports_embeddings: bool = False
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ProviderResponse:
    text: str
    model: str
    provider: ProviderType
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class EmbeddingResponse:
    embeddings: list[list[float]]
    model: str
    provider: ProviderType
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0


class BaseProvider(ABC):
    def __init__(self, config: ModelConfig):
        self.config = config
        self._stats = {"calls": 0, "errors": 0, "total_latency": 0.0, "tokens_in": 0, "tokens_out": 0}
        self._rate_limit = {"max_per_minute": 60, "tokens_per_minute": 0, "last_reset": time.time(), "count": 0}

    @abstractmethod
    def generate(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse: ...

    @abstractmethod
    def generate_stream(self, prompt: str, system: str = "", **kwargs) -> Generator[str, None, None]: ...

    @abstractmethod
    async def generate_async(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse: ...

    @abstractmethod
    async def generate_stream_async(self, prompt: str, system: str = "", **kwargs) -> AsyncGenerator[str, None]: ...

    def tools(self, prompt: str, tools: list[ToolDefinition], system: str = "", **kwargs) -> tuple[str, list[ToolCall]]:
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")

    async def tools_async(self, prompt: str, tools: list[ToolDefinition], system: str = "", **kwargs) -> tuple[str, list[ToolCall]]:
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")

    def reason(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        return self.generate(prompt, system, temperature=0.3, **kwargs)

    async def reason_async(self, prompt: str, system: str = "", **kwargs) -> ProviderResponse:
        return await self.generate_async(prompt, system, temperature=0.3, **kwargs)

    def embed(self, texts: list[str]) -> EmbeddingResponse:
        raise NotImplementedError(f"{self.__class__.__name__} does not support embeddings")

    def vision(self, image: str | bytes, prompt: str = "", **kwargs) -> ProviderResponse:
        raise NotImplementedError(f"{self.__class__.__name__} does not support vision")

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def _check_rate_limit(self) -> bool:
        now = time.time()
        if now - self._rate_limit["last_reset"] > 60:
            self._rate_limit["count"] = 0
            self._rate_limit["last_reset"] = now
        if self._rate_limit["count"] >= self._rate_limit["max_per_minute"]:
            return False
        self._rate_limit["count"] += 1
        return True

    def get_stats(self) -> dict:
        return dict(self._stats)

    def get_rate_limit_status(self) -> dict:
        now = time.time()
        reset_in = 60 - (now - self._rate_limit["last_reset"])
        return {
            "used": self._rate_limit["count"],
            "limit": self._rate_limit["max_per_minute"],
            "reset_in_seconds": max(0, reset_in),
        }

    def _record_call(self, latency: float, tokens_in: int = 0, tokens_out: int = 0, error: bool = False):
        self._stats["calls"] += 1
        self._stats["total_latency"] += latency
        self._stats["tokens_in"] += tokens_in
        self._stats["tokens_out"] += tokens_out
        if error:
            self._stats["errors"] += 1

    def __repr__(self):
        return f"{self.__class__.__name__}(model={self.config.model})"


class ProviderManager:
    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._models: dict[str, ModelConfig] = {}
        self._routing_rules: list[tuple] = []
        self._default_provider: Optional[str] = None
        self._cache: dict[str, tuple[ProviderResponse, float]] = {}
        self._cache_ttl = 300.0
        self._fallback_chain: list[str] = []
        self._load_balancer_index: dict[str, int] = {}
        self._logger = logging.getLogger("provider_manager")

    def register(self, name: str, provider: BaseProvider):
        self._providers[name] = provider
        self._models[name] = provider.config
        if self._default_provider is None:
            self._default_provider = name
        self._load_balancer_index[name] = 0
        self._logger.info(f"Registered provider: {name} ({provider.config.model})")

    def unregister(self, name: str):
        self._providers.pop(name, None)
        self._models.pop(name, None)
        self._load_balancer_index.pop(name, None)
        if self._default_provider == name:
            self._default_provider = next(iter(self._providers)) if self._providers else None

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name)

    def get_model(self, name: str) -> Optional[ModelConfig]:
        return self._models.get(name)

    def set_default(self, name: str):
        if name in self._providers:
            self._default_provider = name

    def add_fallback(self, *names: str):
        self._fallback_chain = list(names)

    def add_routing_rule(self, condition, provider_name: str, priority: int = 0):
        self._routing_rules.append((condition, provider_name, priority))
        self._routing_rules.sort(key=lambda x: -x[2])

    def register(self, name: str, provider: BaseProvider):
        self._providers[name] = provider
        self._models[name] = provider.config
        if self._default_provider is None:
            self._default_provider = name
        self._logger.info(f"Registered provider: {name} ({provider.config.model})")

    def unregister(self, name: str):
        self._providers.pop(name, None)
        self._models.pop(name, None)
        if self._default_provider == name:
            self._default_provider = next(iter(self._providers)) if self._providers else None

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name)

    def get_model(self, name: str) -> Optional[ModelConfig]:
        return self._models.get(name)

    def set_default(self, name: str):
        if name in self._providers:
            self._default_provider = name

    def add_fallback(self, *names: str):
        self._fallback_chain = list(names)

    def add_routing_rule(self, condition, provider_name: str, priority: int = 0):
        self._routing_rules.append((condition, provider_name, priority))
        self._routing_rules.sort(key=lambda x: -x[2])

    def _select_provider(self, prompt: str = "", task_type: str = "") -> str:
        if self._routing_rules:
            for condition, provider_name, priority in self._routing_rules:
                if condition(prompt=prompt, task_type=task_type):
                    if provider_name in self._providers:
                        return provider_name

        if self._default_provider and self._default_provider in self._providers:
            return self._get_healthy_provider(self._default_provider)

        if self._providers:
            return self._get_healthy_provider(next(iter(self._providers)))

        raise RuntimeError("No providers registered")

    def _get_healthy_provider(self, preferred: str) -> str:
        if preferred in self._providers:
            prov = self._providers[preferred]
            if prov._check_rate_limit():
                return preferred
        for name in self._fallback_chain:
            if name in self._providers:
                prov = self._providers[name]
                if prov._check_rate_limit():
                    return name
        return preferred

    def _select_with_load_balance(self, task_type: str = "") -> str:
        candidates = [self._default_provider] + self._fallback_chain if self._default_provider else list(self._providers.keys())
        candidates = [n for n in candidates if n in self._providers]
        if not candidates:
            raise RuntimeError("No providers registered")
        candidates = [n for n in candidates if self._providers[n]._check_rate_limit()]
        if not candidates:
            candidates = [n for n in candidates if n in self._providers]
        idx = self._load_balancer_index.get(task_type, 0) % len(candidates)
        self._load_balancer_index[task_type] = idx + 1
        return candidates[idx]

    def _get_cache_key(self, provider: str, prompt: str, system: str) -> str:
        return f"{provider}:{hash(prompt)}:{hash(system)}"

    def _check_cache(self, key: str) -> Optional[ProviderResponse]:
        entry = self._cache.get(key)
        if entry and (time.time() - entry[1]) < self._cache_ttl:
            return entry[0]
        return None

    def _set_cache(self, key: str, response: ProviderResponse):
        self._cache[key] = (response, time.time())
        if len(self._cache) > 1000:
            old_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][1])[:200]
            for k in old_keys:
                self._cache.pop(k, None)

    def generate(self, prompt: str, system: str = "", provider: str = "", task_type: str = "", use_cache: bool = True, **kwargs) -> ProviderResponse:
        provider_name = provider or self._select_provider(prompt, task_type)

        if use_cache:
            cache_key = self._get_cache_key(provider_name, prompt, system)
            cached = self._check_cache(cache_key)
            if cached:
                return cached

        providers_to_try = [provider_name] + [p for p in self._fallback_chain if p != provider_name]

        last_error = None
        for name in providers_to_try:
            prov = self._providers.get(name)
            if not prov:
                continue
            try:
                response = prov.generate(prompt, system, **kwargs)
                if use_cache:
                    self._set_cache(self._get_cache_key(name, prompt, system), response)
                return response
            except Exception as e:
                last_error = e
                self._logger.warning(f"Provider {name} failed: {e}. Trying fallback...")
                continue

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def generate_async(self, prompt: str, system: str = "", provider: str = "", task_type: str = "", use_cache: bool = True, **kwargs) -> ProviderResponse:
        provider_name = provider or self._select_provider(prompt, task_type)

        if use_cache:
            cache_key = self._get_cache_key(provider_name, prompt, system)
            cached = self._check_cache(cache_key)
            if cached:
                return cached

        providers_to_try = [provider_name] + [p for p in self._fallback_chain if p != provider_name]

        last_error = None
        for name in providers_to_try:
            prov = self._providers.get(name)
            if not prov:
                continue
            try:
                response = await prov.generate_async(prompt, system, **kwargs)
                if use_cache:
                    self._set_cache(self._get_cache_key(name, prompt, system), response)
                return response
            except Exception as e:
                last_error = e
                self._logger.warning(f"Provider {name} async failed: {e}. Trying fallback...")
                continue

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    def generate_stream(self, prompt: str, system: str = "", provider: str = "", task_type: str = "", **kwargs) -> Generator[str, None, None]:
        provider_name = provider or self._select_provider(prompt, task_type)
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        yield from prov.generate_stream(prompt, system, **kwargs)

    async def generate_stream_async(self, prompt: str, system: str = "", provider: str = "", task_type: str = "", **kwargs) -> AsyncGenerator[str, None]:
        provider_name = provider or self._select_provider(prompt, task_type)
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        async for chunk in prov.generate_stream_async(prompt, system, **kwargs):
            yield chunk

    def embed(self, texts: list[str], provider: str = "") -> EmbeddingResponse:
        provider_name = provider or self._default_provider or next(iter(self._providers))
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        return prov.embed(texts)

    def vision(self, image: str | bytes, prompt: str = "", provider: str = "", **kwargs) -> ProviderResponse:
        provider_name = provider or self._select_provider(prompt, "vision")
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        return prov.vision(image, prompt, **kwargs)

    def tools(self, prompt: str, tools: list[ToolDefinition], system: str = "", provider: str = "", task_type: str = "tools", **kwargs) -> tuple[str, list[ToolCall]]:
        provider_name = provider or self._select_provider(prompt, task_type)
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        return prov.tools(prompt, tools, system, **kwargs)

    async def tools_async(self, prompt: str, tools: list[ToolDefinition], system: str = "", provider: str = "", task_type: str = "tools", **kwargs) -> tuple[str, list[ToolCall]]:
        provider_name = provider or self._select_provider(prompt, task_type)
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        return await prov.tools_async(prompt, tools, system, **kwargs)

    def reason(self, prompt: str, system: str = "", provider: str = "", task_type: str = "reasoning", **kwargs) -> ProviderResponse:
        provider_name = provider or self._select_provider(prompt, task_type)
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        return prov.reason(prompt, system, **kwargs)

    async def reason_async(self, prompt: str, system: str = "", provider: str = "", task_type: str = "reasoning", **kwargs) -> ProviderResponse:
        provider_name = provider or self._select_provider(prompt, task_type)
        prov = self._providers.get(provider_name)
        if not prov:
            raise RuntimeError(f"Provider '{provider_name}' not found")
        return await prov.reason_async(prompt, system, **kwargs)

    def get_stats(self) -> dict:
        stats = {}
        for name, prov in self._providers.items():
            stats[name] = prov.get_stats()
        return stats

    def list_providers(self) -> list[dict]:
        return [
            {
                "name": name,
                "model": prov.config.model,
                "provider_type": prov.config.provider.value,
                "supports_streaming": prov.config.supports_streaming,
                "supports_vision": prov.config.supports_vision,
                "supports_tools": prov.config.supports_tools,
                "supports_embeddings": prov.config.supports_embeddings,
            }
            for name, prov in self._providers.items()
        ]

    def clear_cache(self):
        self._cache.clear()

    def __repr__(self):
        return f"ProviderManager(providers={list(self._providers.keys())})"


_manager_instance = None


def get_manager() -> ProviderManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ProviderManager()
    return _manager_instance
