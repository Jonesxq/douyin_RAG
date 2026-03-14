from __future__ import annotations

import sys
import time
from typing import Iterable

from app.core.config import get_settings

settings = get_settings()


class ChromaService:
    def __init__(self) -> None:
        if sys.version_info >= (3, 14):
            raise RuntimeError(
                "ChromaDB is currently incompatible with Python 3.14 in this setup. "
                "Please use Python 3.12 (recommended) and run: uv sync --project backend --python 3.12"
            )

        import chromadb

        self.client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": settings.chroma_distance},
        )

    def delete_by_source_item(self, source_item_id: int) -> None:
        self.collection.delete(where={"source_item_id": int(source_item_id)})

    def upsert_vectors(
        self,
        chunk_ids: Iterable[int],
        source_item_ids: Iterable[int],
        langs: Iterable[str],
        embeddings: Iterable[list[float]],
    ) -> None:
        now_ts = int(time.time())
        ids = [str(x) for x in chunk_ids]
        source_ids = [int(x) for x in source_item_ids]
        lang_list = [x[:16] for x in langs]
        vector_list = list(embeddings)

        if not ids:
            return

        metadatas = [
            {
                "chunk_id": int(ids[idx]),
                "source_item_id": source_ids[idx],
                "lang": lang_list[idx],
                "created_at": now_ts,
            }
            for idx in range(len(ids))
        ]

        documents = ["" for _ in ids]
        self.collection.upsert(ids=ids, embeddings=vector_list, metadatas=metadatas, documents=documents)

    def _distance_to_score(self, distance: float) -> float:
        if settings.chroma_distance == "cosine":
            return 1.0 - float(distance)
        if settings.chroma_distance == "l2":
            return -float(distance)
        return float(distance)

    def search(self, query_vector: list[float], top_k: int = 20) -> list[dict]:
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["metadatas", "distances"],
        )

        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]

        hits: list[dict] = []
        for idx, metadata in enumerate(metadatas):
            if not metadata:
                continue
            chunk_id = metadata.get("chunk_id")
            source_item_id = metadata.get("source_item_id")
            if chunk_id is None or source_item_id is None:
                continue

            distance = distances[idx] if idx < len(distances) else 0.0
            hits.append(
                {
                    "chunk_id": int(chunk_id),
                    "source_item_id": int(source_item_id),
                    "score": self._distance_to_score(float(distance)),
                }
            )
        return hits


_chroma_service: ChromaService | None = None


def get_chroma_service() -> ChromaService:
    global _chroma_service
    if _chroma_service is None:
        _chroma_service = ChromaService()
    return _chroma_service
