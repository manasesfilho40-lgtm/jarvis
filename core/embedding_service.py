import asyncio
import logging
import time
from typing import Optional

import numpy as np

logger = logging.getLogger("embedding_service")

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class EmbeddingService:
    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        self._model = model
        self._cache: dict[str, list[float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_embeddings = 0
        self._ollama_client = None
        self._sentence_model = None

    def _load_sentence_model(self):
        if self._sentence_model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer(self._model)
            logger.info(f"Loaded sentence model: {self._model}")
        except ImportError:
            logger.warning("sentence-transformers not installed, using ollama fallback")

    def _get_ollama_embeddings(self, texts: list[str]) -> list[list[float]]:
        if self._ollama_client is None:
            try:
                import ollama
                self._ollama_client = ollama
            except ImportError:
                logger.error("ollama not installed")
                return [np.zeros(384).tolist() for _ in texts]
        results = []
        for text in texts:
            try:
                resp = self._ollama_client.embeddings(model="nomic-embed-text", prompt=text)
                results.append(resp["embedding"])
            except Exception:
                results.append(np.zeros(384).tolist())
        return results

    def embed(self, text: str) -> list[float]:
        cached = self._cache.get(text)
        if cached is not None:
            self._cache_hits += 1
            return cached

        self._cache_misses += 1
        embedding = self._embed_single(text)
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[text] = embedding
        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        uncached = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                results.append(cached)
                self._cache_hits += 1
            else:
                results.append(None)
                uncached.append(text)
                uncached_indices.append(i)
                self._cache_misses += 1

        if uncached:
            batch_results = self._embed_batch(uncached)
            for idx, emb in zip(uncached_indices, batch_results):
                results[idx] = emb
                if len(self._cache) < 5000:
                    self._cache[texts[idx]] = emb

        return results

    def _embed_single(self, text: str) -> list[float]:
        self._total_embeddings += 1
        if self._sentence_model is not None:
            emb = self._sentence_model.encode(text)
            return emb.tolist()
        try:
            import ollama
            resp = ollama.embeddings(model="nomic-embed-text", prompt=text)
            return resp["embedding"]
        except Exception:
            return np.zeros(384).tolist()

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._total_embeddings += len(texts)
        if self._sentence_model is not None:
            embs = self._sentence_model.encode(texts)
            return [e.tolist() for e in embs]
        return [self._embed_single(t) for t in texts]

    def similarity(self, a: list[float], b: list[float]) -> float:
        a_arr = np.array(a, dtype=np.float32)
        b_arr = np.array(b, dtype=np.float32)
        if np.linalg.norm(a_arr) == 0 or np.linalg.norm(b_arr) == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))

    def get_stats(self) -> dict:
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._cache),
            "total_embeddings": self._total_embeddings,
            "model": self._model,
        }


_embedding_service_instance = None


def get_embedding_service(model: str = "all-MiniLM-L6-v2") -> EmbeddingService:
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService(model=model)
    return _embedding_service_instance
