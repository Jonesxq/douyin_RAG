from __future__ import annotations

import re
import time
from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChatMessage, ChatSession, Chunk
from app.schemas import ChatResponse, ChunkHit
from app.services.chroma_service import get_chroma_service
from app.services.llm_service import QwenClient

settings = get_settings()


class RagService:
    def __init__(self) -> None:
        self.qwen: QwenClient | None = None

    def _get_qwen(self) -> QwenClient:
        if self.qwen is None:
            self.qwen = QwenClient()
        return self.qwen

    def _normalize_query(self, query: str) -> str:
        query = query.strip()
        query = re.sub(r"\s+", " ", query)
        return query

    def _extract_terms(self, query: str) -> list[str]:
        terms = [x.strip().lower() for x in re.split(r"\s+", query) if x.strip()]
        if not terms and query:
            terms = [query.lower()]
        return terms[:8]

    def _detect_style(self, query: str) -> str:
        if re.search(r"总结|对比|区别|优缺点|框架", query):
            return "B"
        if re.search(r"步骤|怎么|如何|具体|哪一|什么时候|参数", query):
            return "A"
        return "C"

    def _dense_retrieve(self, db: Session, normalized_query: str) -> list[dict]:
        qwen = self._get_qwen()
        query_embedding = qwen.embed_texts([normalized_query])[0]
        chroma = get_chroma_service()
        hits = chroma.search(query_embedding, top_k=settings.rag_topk_dense)
        if not hits:
            return []

        chunk_ids = [hit["chunk_id"] for hit in hits]
        rows = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
        row_map = {row.id: row for row in rows}

        normalized: list[dict] = []
        for hit in hits:
            row = row_map.get(hit["chunk_id"])
            if not row:
                continue
            normalized.append(
                {
                    "chunk_id": row.id,
                    "source_item_id": row.source_item_id,
                    "score": hit["score"],
                    "text": row.text_clean,
                }
            )
        return normalized

    def _lexical_score(self, text: str, normalized_query: str, terms: list[str]) -> float:
        text_l = text.lower()
        score = 0.0
        if normalized_query and normalized_query.lower() in text_l:
            score += 3.0
        for term in terms:
            if term in text_l:
                score += 1.0
        return score

    def _fts_retrieve(self, db: Session, normalized_query: str) -> list[dict]:
        terms = self._extract_terms(normalized_query)
        base_query = db.query(Chunk)

        if terms:
            clauses = [Chunk.fts_text.ilike(f"%{term}%") for term in terms]
            rows = base_query.filter(or_(*clauses)).limit(settings.rag_topk_fts * 3).all()
        else:
            rows = base_query.limit(settings.rag_topk_fts).all()

        scored: list[dict] = []
        for row in rows:
            score = self._lexical_score(row.text_clean, normalized_query, terms)
            if score <= 0:
                continue
            scored.append(
                {
                    "chunk_id": row.id,
                    "source_item_id": row.source_item_id,
                    "score": score,
                    "text": row.text_clean,
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: settings.rag_topk_fts]

    def _rrf_fuse(self, dense_hits: list[dict], fts_hits: list[dict]) -> list[dict]:
        k_base = 60
        scores = defaultdict(float)
        payload: dict[int, dict] = {}

        for rank, hit in enumerate(dense_hits, start=1):
            cid = hit["chunk_id"]
            scores[cid] += 1.0 / (k_base + rank)
            payload[cid] = hit

        for rank, hit in enumerate(fts_hits, start=1):
            cid = hit["chunk_id"]
            scores[cid] += 1.0 / (k_base + rank)
            payload[cid] = hit

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        merged: list[dict] = []
        for cid, score in ranked[: settings.rag_context_count]:
            item = payload[cid]
            merged.append(
                {
                    "chunk_id": item["chunk_id"],
                    "source_item_id": item["source_item_id"],
                    "score": score,
                    "text": item["text"],
                }
            )
        return merged

    def _build_prompts(self, query: str, style: str, contexts: list[dict]) -> tuple[str, str]:
        contexts_text = "\n\n".join(
            [f"[chunk:{c['chunk_id']}] {c['text']}" for c in contexts[: settings.rag_context_count]]
        )

        system_prompt = (
            "你是一个视频知识库问答助手。默认优先给出B风格（总结+对比），"
            "其次A风格（定位具体步骤），最后C风格（行动建议）。"
            "回答要准确、简洁、可执行，禁止编造来源。"
        )

        user_prompt = (
            f"问题风格优先级标签: {style}\n"
            f"用户问题: {query}\n"
            "可用上下文:\n"
            f"{contexts_text}\n\n"
            "请基于上下文回答。如果上下文不足，明确说信息不足。"
        )
        return system_prompt, user_prompt

    def answer(self, db: Session, query: str, session_id: int | None) -> ChatResponse:
        started = time.perf_counter()
        normalized_query = self._normalize_query(query)
        style = self._detect_style(normalized_query)

        dense_hits = self._dense_retrieve(db, normalized_query)
        fts_hits = self._fts_retrieve(db, normalized_query)

        merged_hits = self._rrf_fuse(dense_hits, fts_hits)
        system_prompt, user_prompt = self._build_prompts(normalized_query, style, merged_hits)

        answer = self._get_qwen().chat(system_prompt=system_prompt, user_prompt=user_prompt)
        latency_ms = int((time.perf_counter() - started) * 1000)

        session = db.get(ChatSession, session_id) if session_id else None
        if not session:
            title = normalized_query[:40] if normalized_query else "New Chat"
            session = ChatSession(title=title)
            db.add(session)
            db.flush()

        db.add(
            ChatMessage(
                session_id=session.id,
                role="user",
                content=query,
                retrieved_chunk_ids=[x["chunk_id"] for x in merged_hits],
                model=settings.qwen_chat_model,
            )
        )
        db.add(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content=answer,
                retrieved_chunk_ids=[x["chunk_id"] for x in merged_hits],
                model=settings.qwen_chat_model,
                latency_ms=latency_ms,
            )
        )
        db.commit()

        return ChatResponse(
            session_id=session.id,
            answer=answer,
            latency_ms=latency_ms,
            hits=[
                ChunkHit(
                    chunk_id=hit["chunk_id"],
                    source_item_id=hit["source_item_id"],
                    score=round(hit["score"], 6),
                    text=hit["text"],
                )
                for hit in merged_hits
            ],
        )


rag_service = RagService()
