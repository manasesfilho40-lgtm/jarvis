import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("faiss_memory")

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.warning("FAISS not installed. Install with: pip install faiss-cpu")


class FAISSMemory:
    def __init__(self, dimension: int = 384, persist_dir: str = ""):
        self.dimension = dimension
        if not persist_dir:
            persist_dir = str(Path(__file__).resolve().parent / "faiss_store")
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self._indexes: dict[str, Any] = {}
        self._stores: dict[str, list[dict]] = {}
        self._initialized = False

    def _get_or_create_index(self, store_name: str):
        if store_name in self._indexes:
            return self._indexes[store_name]

        index_path = os.path.join(self.persist_dir, f"{store_name}.faiss")
        data_path = os.path.join(self.persist_dir, f"{store_name}.json")

        if HAS_FAISS and os.path.exists(index_path):
            try:
                index = faiss.read_index(index_path)
                self._indexes[store_name] = index
            except Exception:
                index = faiss.IndexFlatL2(self.dimension)
                self._indexes[store_name] = index
        else:
            if HAS_FAISS:
                index = faiss.IndexFlatL2(self.dimension)
                self._indexes[store_name] = index
            else:
                self._indexes[store_name] = None

        if os.path.exists(data_path):
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    self._stores[store_name] = json.load(f)
            except Exception:
                self._stores[store_name] = []
        else:
            self._stores[store_name] = []

        return self._indexes[store_name]

    def add(self, text: str, embedding: list[float], store_name: str = "default", metadata: dict = None) -> str:
        entry_id = str(uuid.uuid4())[:12]
        index = self._get_or_create_index(store_name)

        entry = {
            "id": entry_id,
            "text": text,
            "metadata": metadata or {},
            "timestamp": time.time(),
            "_embedding": embedding,
        }
        self._stores[store_name].append(entry)

        if index is not None and HAS_FAISS:
            emb_array = np.array([embedding], dtype=np.float32)
            if emb_array.shape[1] != self.dimension:
                emb_array = self._pad_or_truncate(emb_array)
            index.add(emb_array)

        self._save_store(store_name)
        return entry_id

    def search(self, query_embedding: list[float], store_name: str = "default", n_results: int = 5) -> list[dict]:
        index = self._get_or_create_index(store_name)
        store = self._stores.get(store_name, [])

        if index is not None and HAS_FAISS and index.ntotal > 0:
            query_array = np.array([query_embedding], dtype=np.float32)
            if query_array.shape[1] != self.dimension:
                query_array = self._pad_or_truncate(query_array)
            distances, indices = index.search(query_array, min(n_results, index.ntotal))
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < len(store):
                    entry = store[idx]
                    results.append({
                        "id": entry["id"],
                        "text": entry["text"],
                        "metadata": entry["metadata"],
                        "score": float(1.0 / (1.0 + distances[0][i])),
                        "timestamp": entry.get("timestamp", 0),
                    })
            return results
        else:
            scored = []
            for entry in store:
                sim = self._cosine_similarity(query_embedding, entry.get("_embedding"))
                scored.append((sim, entry))
            scored.sort(key=lambda x: -x[0])
            return [
                {
                    "id": e["id"], "text": e["text"],
                    "metadata": e.get("metadata", {}),
                    "score": s,
                    "timestamp": e.get("timestamp", 0),
                }
                for s, e in scored[:n_results]
            ]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not b:
            return 0.0
        a_arr = np.array(a, dtype=np.float32)
        b_arr = np.array(b, dtype=np.float32)
        if np.linalg.norm(a_arr) == 0 or np.linalg.norm(b_arr) == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))

    def _pad_or_truncate(self, arr: np.ndarray) -> np.ndarray:
        if arr.shape[1] < self.dimension:
            pad = np.zeros((arr.shape[0], self.dimension - arr.shape[1]), dtype=np.float32)
            return np.concatenate([arr, pad], axis=1)
        return arr[:, :self.dimension]

    def _save_store(self, store_name: str):
        data_path = os.path.join(self.persist_dir, f"{store_name}.json")
        try:
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(self._stores.get(store_name, []), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save FAISS store {store_name}: {e}")

    def save_all(self):
        for store_name in self._stores:
            self._save_store(store_name)
            index = self._indexes.get(store_name)
            if index is not None and HAS_FAISS:
                index_path = os.path.join(self.persist_dir, f"{store_name}.faiss")
                try:
                    faiss.write_index(index, index_path)
                except Exception as e:
                    logger.error(f"Failed to save FAISS index {store_name}: {e}")

    def get_count(self, store_name: str = "default") -> int:
        return len(self._stores.get(store_name, []))

    def get_all_stores(self) -> dict[str, int]:
        return {name: len(store) for name, store in self._stores.items()}

    def clear(self, store_name: str = None):
        if store_name:
            self._stores[store_name] = []
            if store_name in self._indexes:
                if HAS_FAISS:
                    self._indexes[store_name] = faiss.IndexFlatL2(self.dimension)
                else:
                    self._indexes[store_name] = None
            self._save_store(store_name)
        else:
            for name in list(self._stores.keys()):
                self.clear(name)

    def close(self):
        self.save_all()


_faiss_memory_instance = None


def get_faiss_memory(dimension: int = 384) -> FAISSMemory:
    global _faiss_memory_instance
    if _faiss_memory_instance is None:
        _faiss_memory_instance = FAISSMemory(dimension=dimension)
    return _faiss_memory_instance
