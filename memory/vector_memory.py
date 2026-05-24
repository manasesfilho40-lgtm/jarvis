import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("vector_memory")


try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    logger.warning("ChromaDB not installed. Vector memory will use file-based fallback.")


class MemoryStore(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    WORKING = "working"
    CONVERSATIONS = "conversations"
    OBSERVATIONS = "observations"
    SUMMARIES = "summaries"
    PROJECTS = "projects"
    USER_PROFILE = "user_profile"
    EXPERIENCES = "experiences"
    SKILLS = "skills"


@dataclass
class MemoryEntry:
    id: str
    content: str
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    embedding: Optional[list[float]] = None
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "score": self.score,
        }


class MemoryStore(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    WORKING = "working"
    CONVERSATIONS = "conversations"
    OBSERVATIONS = "observations"
    SUMMARIES = "summaries"
    PROJECTS = "projects"
    USER_PROFILE = "user_profile"
    EXPERIENCES = "experiences"
    SKILLS = "skills"


class VectorMemory:
    def __init__(self, persist_dir: str = ""):
        if not persist_dir:
            persist_dir = str(Path(__file__).resolve().parent / "vector_store")
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self._collections: dict[str, Any] = {}
        self._fallback_store: dict[str, list[MemoryEntry]] = {}
        self._client = None
        self._initialized = False
        self._embedding_function = None

    def _init_chromadb(self):
        if self._initialized:
            return
        self._initialized = True

        if not HAS_CHROMADB:
            logger.info("ChromaDB not available, using file-based fallback memory")
            return

        try:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            logger.info(f"ChromaDB initialized at {self.persist_dir}")
        except Exception as e:
            logger.warning(f"Failed to init ChromaDB: {e}. Using file fallback.")
            self._client = None

    def _get_collection(self, store: MemoryStore):
        self._init_chromadb()

        if self._client:
            collection_name = store.value
            if collection_name not in self._collections:
                try:
                    col = self._client.get_or_create_collection(
                        name=collection_name,
                        metadata={"store": store.value, "created": str(datetime.now())},
                    )
                    self._collections[collection_name] = col
                except Exception as e:
                    logger.error(f"Failed to get/create collection {collection_name}: {e}")
                    return None
            return self._collections.get(collection_name)

        return None

    def _fallback_store_get(self, store: MemoryStore) -> list[MemoryEntry]:
        key = store.value
        if key not in self._fallback_store:
            self._fallback_store[key] = []
            fallback_file = Path(self.persist_dir) / f"{key}.json"
            if fallback_file.exists():
                try:
                    with open(fallback_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for item in data:
                            self._fallback_store[key].append(MemoryEntry(**item))
                except Exception as e:
                    logger.error(f"Failed to load fallback store {key}: {e}")
        return self._fallback_store[key]

    def _save_fallback(self, store: MemoryStore):
        key = store.value
        entries = self._fallback_store.get(key, [])
        fallback_file = Path(self.persist_dir) / f"{key}.json"
        try:
            with open(fallback_file, "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in entries], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save fallback store {key}: {e}")

    def store(self, content: str, store: MemoryStore = MemoryStore.EPISODIC, metadata: dict | None = None, embedding: list[float] | None = None) -> str:
        entry_id = str(uuid.uuid4())[:12]
        metadata = metadata or {}
        metadata["stored_at"] = datetime.now().isoformat()

        collection = self._get_collection(store)
        if collection is not None:
            try:
                collection.add(
                    ids=[entry_id],
                    documents=[content],
                    metadatas=[metadata],
                    embeddings=[embedding] if embedding else None,
                )
                logger.debug(f"Stored in ChromaDB[{store.value}]: {content[:50]}...")
                return entry_id
            except Exception as e:
                logger.error(f"ChromaDB store failed: {e}. Falling back.")

        entries = self._fallback_store_get(store)
        entries.append(MemoryEntry(id=entry_id, content=content, metadata=metadata))
        self._save_fallback(store)
        logger.debug(f"Stored in fallback[{store.value}]: {content[:50]}...")
        return entry_id

    def search(self, query: str, store: MemoryStore = MemoryStore.EPISODIC, n_results: int = 5, threshold: float = 0.0) -> list[MemoryEntry]:
        collection = self._get_collection(store)
        if collection is not None:
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                )
                entries = []
                if results["ids"] and results["ids"][0]:
                    for i, doc_id in enumerate(results["ids"][0]):
                        entry = MemoryEntry(
                            id=doc_id,
                            content=results["documents"][0][i] if results["documents"] else "",
                            metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                            score=results["distances"][0][i] if results.get("distances") else 0.0,
                        )
                        if entry.score >= threshold:
                            entries.append(entry)
                return entries
            except Exception as e:
                logger.error(f"ChromaDB search failed: {e}. Falling back.")

        entries = self._fallback_store_get(store)
        query_lower = query.lower()
        scored = []
        for entry in entries:
            score = 0.0
            if query_lower in entry.content.lower():
                score = 1.0
            elif any(q in entry.content.lower() for q in query_lower.split()):
                score = 0.5
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        return [entry for score, entry in scored[:n_results] if score >= threshold]

    def get_all(self, store: MemoryStore, limit: int = 100) -> list[MemoryEntry]:
        collection = self._get_collection(store)
        if collection is not None:
            try:
                results = collection.get(limit=limit)
                entries = []
                if results["ids"]:
                    for i, doc_id in enumerate(results["ids"]):
                        entries.append(MemoryEntry(
                            id=doc_id,
                            content=results["documents"][i] if results["documents"] else "",
                            metadata=results["metadatas"][i] if results["metadatas"] else {},
                        ))
                return entries
            except Exception as e:
                logger.error(f"ChromaDB get_all failed: {e}. Falling back.")

        entries = self._fallback_store_get(store)
        return entries[-limit:]

    def delete(self, entry_id: str, store: MemoryStore):
        collection = self._get_collection(store)
        if collection is not None:
            try:
                collection.delete(ids=[entry_id])
                return
            except Exception as e:
                logger.error(f"ChromaDB delete failed: {e}")

        entries = self._fallback_store_get(store)
        self._fallback_store[store.value] = [e for e in entries if e.id != entry_id]
        self._save_fallback(store)

    def clear(self, store: Optional[MemoryStore] = None):
        stores = [store] if store else list(MemoryStore)
        for s in stores:
            collection = self._get_collection(s)
            if collection is not None:
                try:
                    self._client.delete_collection(s.value)
                    self._collections.pop(s.value, None)
                    continue
                except Exception:
                    pass
            self._fallback_store[s.value] = []
            self._save_fallback(s)

    def count(self, store: Optional[MemoryStore] = None) -> dict[str, int]:
        counts = {}
        stores = [store] if store else list(MemoryStore)
        for s in stores:
            collection = self._get_collection(s)
            if collection is not None:
                try:
                    counts[s.value] = collection.count()
                    continue
                except Exception:
                    pass
            counts[s.value] = len(self._fallback_store.get(s.value, []))
        return counts

    def get_recent(self, store: MemoryStore, n: int = 10) -> list[MemoryEntry]:
        all_entries = self.get_all(store)
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)
        return all_entries[:n]

    def get_context(self, query: str, n_results: int = 5, stores: Optional[list[MemoryStore]] = None) -> str:
        if stores is None:
            stores = [MemoryStore.EPISODIC, MemoryStore.SEMANTIC, MemoryStore.CONVERSATIONS]

        results = []
        for store in stores:
            entries = self.search(query, store=store, n_results=n_results)
            for entry in entries:
                results.append(f"[{store.value}] {entry.content}")

        return "\n".join(results) if results else ""

    def close(self):
        self._client = None
        self._collections.clear()


_vector_memory_instance = None


def get_vector_memory(persist_dir: str = "") -> VectorMemory:
    global _vector_memory_instance
    if _vector_memory_instance is None:
        _vector_memory_instance = VectorMemory(persist_dir)
    return _vector_memory_instance

