from __future__ import annotations

"""Chroma 向量库封装：upsert、delete、search、count。"""

import sys
import time
from typing import Iterable

from app.core.config import get_settings

settings = get_settings()


class ChromaService:
    def __init__(self) -> None:
        """
        功能：初始化 ChromaService 的实例状态。
        参数：
        - 无。
        返回值：
        - None：构造函数不返回业务值。
        """
        if sys.version_info >= (3, 14):
            raise RuntimeError(
                "ChromaDB is currently incompatible with Python 3.14 in this setup. "
                "Please use Python 3.12 and run: uv sync --project backend --python 3.12"
            )

        import chromadb

        self.client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": settings.chroma_distance},
        )

    def delete_videos(self, platform_item_ids: Iterable[str]) -> None:
        """
        功能：删除 ChromaService.delete_videos 对应的资源或记录。
        参数：
        - platform_item_ids：输入参数。
        返回值：
        - None：函数处理结果。
        """
        ids = [item for item in platform_item_ids if item]
        if not ids:
            return
        self.collection.delete(where={"platform_item_id": {"$in": ids}})

    def upsert_video_chunks(
        self,
        platform_item_id: str,
        title: str,
        collection_ids: list[str],
        chunks: list[str],
        embeddings: list[list[float]],
        lang: str,
        source: str,
    ) -> list[str]:
        """
        功能：执行 ChromaService.upsert_video_chunks 的核心业务逻辑。
        参数：
        - platform_item_id：输入参数。
        - title：输入参数。
        - collection_ids：输入参数。
        - chunks：输入参数。
        - embeddings：输入参数。
        - lang：输入参数。
        - source：输入参数。
        返回值：
        - list[str]：函数处理结果。
        """
        if not chunks:
            return []

        now_ts = int(time.time())
        chunk_ids = [f"{platform_item_id}:{idx}" for idx in range(len(chunks))]
        metadatas = [
            {
                "chunk_id": chunk_ids[idx],
                "platform_item_id": platform_item_id,
                "chunk_index": idx,
                "title": title[:255],
                "collection_ids": ",".join(sorted(set(collection_ids)))[:1024],
                "lang": lang[:16],
                "source": source[:32],
                "created_at": now_ts,
            }
            for idx in range(len(chunks))
        ]

        self.collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks,
        )
        return chunk_ids

    def _distance_to_score(self, distance: float) -> float:
        """
        功能：执行 ChromaService._distance_to_score 的内部处理逻辑。
        参数：
        - distance：输入参数。
        返回值：
        - float：函数处理结果。
        """
        if settings.chroma_distance == "cosine":
            return 1.0 - float(distance)
        if settings.chroma_distance == "l2":
            return -float(distance)
        return float(distance)

    def search(self, query_vector: list[float], top_k: int = 20) -> list[dict]:
        """
        功能：执行 ChromaService.search 的核心业务逻辑。
        参数：
        - query_vector：输入参数。
        - top_k：输入参数。
        返回值：
        - list[dict]：函数处理结果。
        """
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["metadatas", "distances", "documents"],
        )

        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]

        hits: list[dict] = []
        for idx, metadata in enumerate(metadatas):
            if not metadata:
                continue
            chunk_id = ids[idx] if idx < len(ids) else metadata.get("chunk_id")
            platform_item_id = metadata.get("platform_item_id")
            title = metadata.get("title", "")
            if not chunk_id or not platform_item_id:
                continue

            distance = distances[idx] if idx < len(distances) else 0.0
            text = documents[idx] if idx < len(documents) else ""
            hits.append(
                {
                    "chunk_id": str(chunk_id),
                    "platform_item_id": str(platform_item_id),
                    "title": str(title or ""),
                    "collection_ids": str(metadata.get("collection_ids") or ""),
                    "score": self._distance_to_score(float(distance)),
                    "text": str(text or ""),
                }
            )
        return hits

    def count(self) -> int:
        """
        功能：执行 ChromaService.count 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - int：函数处理结果。
        """
        return int(self.collection.count())


_chroma_service: ChromaService | None = None


def get_chroma_service() -> ChromaService:
    """
    功能：获取 get_chroma_service 对应的数据或对象。
    参数：
    - 无。
    返回值：
    - ChromaService：函数处理结果。
    """
    global _chroma_service
    if _chroma_service is None:
        _chroma_service = ChromaService()
    return _chroma_service
