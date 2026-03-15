from __future__ import annotations

"""RAG 服务：查询路由、混合检索、答案生成、会话落库。"""

import logging
import re
import time
from collections import defaultdict
from typing import Iterable

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChatMessage, ChatSession, FavoriteCollection, FavoriteVideo, VideoCache
from app.schemas import (
    ChatAskResponse,
    ChatHit,
    ChatMessageDTO,
    ChatMessagesResponse,
    ChatSessionDTO,
    ChatSessionsResponse,
)
from app.services.chroma_service import get_chroma_service
from app.services.llm_service import QwenClient

settings = get_settings()
logger = logging.getLogger(__name__)


class RagService:
    def __init__(self) -> None:
        """
        功能：初始化 RagService 的实例状态。
        参数：
        - 无。
        返回值：
        - None：构造函数不返回业务值。
        """
        self.qwen: QwenClient | None = None

    def _get_qwen(self) -> QwenClient:
        """
        功能：执行 RagService._get_qwen 的内部处理逻辑。
        参数：
        - 无。
        返回值：
        - QwenClient：函数处理结果。
        """
        if self.qwen is None:
            self.qwen = QwenClient()
        return self.qwen

    @staticmethod
    def _normalize_query(query: str) -> str:
        """
        功能：执行 RagService._normalize_query 的内部处理逻辑。
        参数：
        - query：输入参数。
        返回值：
        - str：函数处理结果。
        """
        query = query.strip()
        query = re.sub(r"\s+", " ", query)
        return query

    @staticmethod
    def _extract_terms(query: str) -> list[str]:
        """
        功能：执行 RagService._extract_terms 的内部处理逻辑。
        参数：
        - query：输入参数。
        返回值：
        - list[str]：函数处理结果。
        """
        terms = [x.strip().lower() for x in re.split(r"\s+", query) if x.strip()]
        if not terms and query:
            terms = [query.lower()]
        return terms[:8]

    @staticmethod
    def _is_general_query(query: str) -> bool:
        """
        功能：执行 RagService._is_general_query 的内部处理逻辑。
        参数：
        - query：输入参数。
        返回值：
        - bool：函数处理结果。
        """
        low = query.lower().strip()
        keywords = ["你好", "在吗", "hi", "hello", "你是谁", "谢谢", "早上好", "晚安"]
        return any(token in low for token in keywords)

    @staticmethod
    def _is_list_query(query: str) -> bool:
        """
        功能：执行 RagService._is_list_query 的内部处理逻辑。
        参数：
        - query：输入参数。
        返回值：
        - bool：函数处理结果。
        """
        return bool(re.search(r"有哪些|列表|清单|目录|都有什么|列出", query))

    @staticmethod
    def _is_summary_query(query: str) -> bool:
        """
        功能：执行 RagService._is_summary_query 的内部处理逻辑。
        参数：
        - query：输入参数。
        返回值：
        - bool：函数处理结果。
        """
        return bool(re.search(r"总结|概述|概括|回顾|梳理|整体|全部|全库", query))

    @staticmethod
    def _is_structured_request(query: str) -> bool:
        """
        功能：执行 RagService._is_structured_request 的内部处理逻辑。
        参数：
        - query：输入参数。
        返回值：
        - bool：函数处理结果。
        """
        return bool(re.search(r"总结|对比|步骤|清单|列表|框架|归纳", query))

    def _route(self, query: str, has_data: bool) -> str:
        # 先走规则路由，必要时再调用 LLM 路由，降低成本并保证可控性。
        """
        功能：执行 RagService._route 的内部处理逻辑。
        参数：
        - query：输入参数。
        - has_data：输入参数。
        返回值：
        - str：函数处理结果。
        """
        if self._is_general_query(query):
            return "direct"

        if self._is_list_query(query):
            return "db_list"

        if self._is_summary_query(query):
            return "db_content"

        llm_route = self._get_qwen().classify_route(query)
        if llm_route:
            return llm_route

        if not has_data:
            return "direct"
        return "vector"

    def _resolve_scope_item_ids(self, db: Session, collection_ids: list[str] | None) -> set[str]:
        """
        功能：执行 RagService._resolve_scope_item_ids 的内部处理逻辑。
        参数：
        - db：输入参数。
        - collection_ids：输入参数。
        返回值：
        - set[str]：函数处理结果。
        """
        if not collection_ids or "all" in collection_ids:
            rows = db.execute(
                select(FavoriteVideo.platform_item_id)
                .where(FavoriteVideo.is_active.is_(True))
                .group_by(FavoriteVideo.platform_item_id)
            ).all()
            return {row[0] for row in rows}

        final_rows = db.execute(
            select(FavoriteVideo.platform_item_id)
            .join(FavoriteCollection, FavoriteCollection.id == FavoriteVideo.collection_id)
            .where(
                FavoriteVideo.is_active.is_(True),
                FavoriteCollection.is_active.is_(True),
                FavoriteCollection.platform_collection_id.in_(collection_ids),
            )
            .group_by(FavoriteVideo.platform_item_id)
        ).all()
        return {row[0] for row in final_rows}

    def _dense_retrieve(self, query: str, scope_ids: set[str]) -> list[dict]:
        """
        功能：执行 RagService._dense_retrieve 的内部处理逻辑。
        参数：
        - query：输入参数。
        - scope_ids：输入参数。
        返回值：
        - list[dict]：函数处理结果。
        """
        if not scope_ids:
            return []

        query_embedding = self._get_qwen().embed_texts([query])[0]
        chroma = get_chroma_service()
        hits = chroma.search(query_embedding, top_k=settings.rag_topk_dense * 3)
        filtered = [hit for hit in hits if hit["platform_item_id"] in scope_ids]
        return filtered[: settings.rag_topk_dense]

    def _lexical_score(self, text: str, normalized_query: str, terms: list[str]) -> float:
        """
        功能：执行 RagService._lexical_score 的内部处理逻辑。
        参数：
        - text：输入参数。
        - normalized_query：输入参数。
        - terms：输入参数。
        返回值：
        - float：函数处理结果。
        """
        text_l = text.lower()
        score = 0.0
        if normalized_query and normalized_query.lower() in text_l:
            score += 3.0
        for term in terms:
            if term in text_l:
                score += 1.0
        return score

    def _fts_retrieve(self, db: Session, query: str, scope_ids: set[str]) -> list[dict]:
        """
        功能：执行 RagService._fts_retrieve 的内部处理逻辑。
        参数：
        - db：输入参数。
        - query：输入参数。
        - scope_ids：输入参数。
        返回值：
        - list[dict]：函数处理结果。
        """
        if not scope_ids:
            return []

        terms = self._extract_terms(query)
        base = db.query(VideoCache).filter(VideoCache.platform_item_id.in_(scope_ids))

        if terms:
            clauses = [
                VideoCache.transcript_text.ilike(f"%{term}%") |
                VideoCache.title.ilike(f"%{term}%")
                for term in terms
            ]
            rows = base.filter(or_(*clauses)).limit(settings.rag_topk_fts * 3).all()
        else:
            rows = base.limit(settings.rag_topk_fts).all()

        scored: list[dict] = []
        for row in rows:
            text = row.transcript_text or ""
            score = self._lexical_score((row.title or "") + "\n" + text, query, terms)
            if score <= 0:
                continue
            scored.append(
                {
                    "chunk_id": f"{row.platform_item_id}:fts",
                    "platform_item_id": row.platform_item_id,
                    "title": row.title,
                    "score": score,
                    "text": text[: settings.rag_excerpt_chars] if text else row.title,
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: settings.rag_topk_fts]

    def _rrf_fuse(self, dense_hits: list[dict], fts_hits: list[dict]) -> list[dict]:
        # 使用 RRF 融合向量召回与关键词召回，兼顾语义与字面匹配。
        """
        功能：执行 RagService._rrf_fuse 的内部处理逻辑。
        参数：
        - dense_hits：输入参数。
        - fts_hits：输入参数。
        返回值：
        - list[dict]：函数处理结果。
        """
        k_base = 60
        scores = defaultdict(float)
        payload: dict[str, dict] = {}

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
                    "platform_item_id": item["platform_item_id"],
                    "title": item.get("title", ""),
                    "score": score,
                    "text": item.get("text", ""),
                }
            )
        return merged

    def _truncate_context(self, context: str, max_chars: int | None = None) -> str:
        """
        Function: Trim oversized context before sending to the model.
        Params:
        - context: Source context text.
        - max_chars: Optional max length.
        Returns:
        - str: Trimmed context string.
        """
        if not context:
            return ""
        cap = max_chars if max_chars is not None else settings.rag_prompt_max_context_chars
        if cap <= 0:
            return context
        if len(context) <= cap:
            return context
        return context[:cap] + "\n\n[context truncated]"
    def _db_list_context(self, db: Session, scope_ids: set[str]) -> str:
        """
        功能：执行 RagService._db_list_context 的内部处理逻辑。
        参数：
        - db：输入参数。
        - scope_ids：输入参数。
        返回值：
        - str：函数处理结果。
        """
        rows = db.query(VideoCache).filter(VideoCache.platform_item_id.in_(scope_ids)).limit(120).all()
        if not rows:
            return ""
        lines = [f"- {row.title} ({row.platform_item_id})" for row in rows]
        return "\n".join(lines)

    def _db_content_context(self, db: Session, scope_ids: set[str]) -> str:
        """
        功能：执行 RagService._db_content_context 的内部处理逻辑。
        参数：
        - db：输入参数。
        - scope_ids：输入参数。
        返回值：
        - str：函数处理结果。
        """
        rows = (
            db.query(VideoCache)
            .filter(VideoCache.platform_item_id.in_(scope_ids), VideoCache.status == "success")
            .order_by(VideoCache.processed_at.desc())
            .limit(settings.rag_db_content_limit)
            .all()
        )
        if not rows:
            return ""

        parts = []
        for row in rows:
            excerpt = (row.transcript_text or "")[: settings.rag_excerpt_chars]
            if not excerpt:
                continue
            parts.append(f"【{row.title}】\n{excerpt}")
        return "\n\n---\n\n".join(parts)

    def _history_context(self, db: Session, session_id: int | None) -> str:
        """
        功能：执行 RagService._history_context 的内部处理逻辑。
        参数：
        - db：输入参数。
        - session_id：输入参数。
        返回值：
        - str：函数处理结果。
        """
        if not session_id:
            return ""

        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(settings.chat_history_window)
            .all()
        )
        if not rows:
            return ""

        rows = list(reversed(rows))
        lines: list[str] = []
        for row in rows:
            role = "用户" if row.role == "user" else "助手"
            content = (row.content or "").strip()
            if not content:
                continue
            if len(content) > settings.chat_max_content_chars:
                content = content[: settings.chat_max_content_chars] + "..."
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    @staticmethod
    def _answer_style_rules(is_structured: bool) -> str:
        """
        功能：执行 RagService._answer_style_rules 的内部处理逻辑。
        参数：
        - is_structured：输入参数。
        返回值：
        - str：函数处理结果。
        """
        if is_structured:
            return (
                "输出要求：\n"
                "1) 语气自然、像对话，不要生硬模板。\n"
                "2) 可用轻结构（最多 3 点），每点用完整句，不要一行一句。\n"
                "3) 禁止 Markdown 表格和标题符号（如 ###、|）。\n"
            )
        return (
            "输出要求：\n"
            "1) 用自然口语化短段落回答，像真人交流。\n"
            "2) 先直接回答，再补充必要细节，默认 2-4 段，段落间要有过渡。\n"
            "3) 禁止 Markdown 表格和标题符号（如 ###、|）。\n"
        )

    @staticmethod
    def _sanitize_answer_text(answer: str, is_structured: bool) -> str:
        """
        功能：执行 RagService._sanitize_answer_text 的内部处理逻辑。
        参数：
        - answer：输入参数。
        - is_structured：输入参数。
        返回值：
        - str：函数处理结果。
        """
        text = (answer or "").replace("\r\n", "\n").strip()
        if not text:
            return text

        text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)

        clean_lines: list[str] = []
        bullet_idx = 0
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                clean_lines.append("")
                continue

            if re.fullmatch(r"[\|\-\:\s]+", line):
                continue

            if "|" in line:
                parts = [part.strip() for part in line.split("|") if part.strip()]
                line = " ".join(parts) if parts else ""
                if not line:
                    continue

            bullet_match = re.match(r"^\s*[-*•]\s+(.*)$", line)
            if bullet_match:
                if is_structured:
                    bullet_idx += 1
                    line = f"{bullet_idx}. {bullet_match.group(1).strip()}"
                else:
                    line = bullet_match.group(1).strip()
            else:
                if is_structured:
                    line = re.sub(r"^\s*(\d+)\)\s*", r"\1. ", line)
                    line = re.sub(r"^\s*(\d+)[、]\s*", r"\1. ", line)

            line = re.sub(r"[`*_]{1,3}", "", line).strip()
            if line:
                clean_lines.append(line)

        merged = "\n".join(clean_lines)
        if not is_structured:
            merged = re.sub(r"(?<![。！？.!?：:])\n(?!\n)", " ", merged)
        merged = re.sub(r"\n{3,}", "\n\n", merged).strip()
        return merged

    def _build_prompts(self, route: str, query: str, context: str, history_context: str) -> tuple[str, str, bool]:
        """
        Function: Build final system/user prompts for answer generation.
        Params:
        - route: Chosen route type.
        - query: Normalized user query.
        - context: Retrieved context text.
        - history_context: Recent chat history text.
        Returns:
        - tuple[str, str, bool]: system prompt, user prompt, structured flag.
        """
        is_structured = self._is_structured_request(query)
        history_block = f"Recent chat history:\n{history_context}\n\n" if history_context else ""

        if route == "direct":
            system = (
                "You are a natural and friendly assistant. Answer conversationally.\n"
                f"{self._answer_style_rules(is_structured)}"
            )
            user = f"{history_block}Current question: {query}"
            return system, user, is_structured

        if route == "db_list":
            system = (
                "You are a favorites knowledge-base assistant. The user asks for a list/catalog."
                " Give the direct conclusion first, then key points.\n"
                f"{self._answer_style_rules(is_structured)}"
            )
            user = f"{history_block}Question: {query}\n\nIndexed videos:\n{context}"
            return system, user, is_structured

        if route == "db_content":
            system = (
                "You are a favorites knowledge-base assistant. The user asks for an overview."
                " Keep the wording natural and concise.\n"
                f"{self._answer_style_rules(is_structured)}"
            )
            user = f"{history_block}Question: {query}\n\nContent:\n{context}"
            return system, user, is_structured

        system = (
            "You are a video knowledge-base QA assistant. Answer from retrieved context."
            " Give a direct conclusion first, then concise evidence.\n"
            f"{self._answer_style_rules(is_structured)}"
        )
        user = f"{history_block}Question: {query}\n\nContext:\n{context}"
        return system, user, is_structured

    def _build_answer(self, route: str, query: str, context: str, history_context: str) -> str:
        """
        Function: Generate a non-streaming answer from prompts.
        Params:
        - route: Chosen route type.
        - query: Normalized query.
        - context: Retrieved context.
        - history_context: Recent chat history.
        Returns:
        - str: Final answer text.
        """
        system, user, is_structured = self._build_prompts(route, query, context, history_context)
        answer = self._get_qwen().chat(
            system_prompt=system,
            user_prompt=user,
            timeout_sec=settings.qwen_chat_timeout_sec,
        )
        return self._sanitize_answer_text(answer, is_structured)
    def _log_timing(self, prefix: str, route: str, total_ms: int, scope_count: int, hit_count: int, stages: dict[str, int]) -> None:
        """
        Function: Write per-stage timing metrics for diagnostics.
        Params:
        - prefix: Log prefix.
        - route: Final route type.
        - total_ms: Total latency in ms.
        - scope_count: Scoped video count.
        - hit_count: Retrieved hit count.
        - stages: Stage timing dictionary.
        Returns:
        - None: Logging side effect only.
        """
        logger.info(
            "%s route=%s total=%sms scope=%s hits=%s stages=%s",
            prefix,
            route,
            total_ms,
            scope_count,
            hit_count,
            stages,
        )
    def answer(
        self,
        db: Session,
        query: str,
        session_id: int | None,
        collection_ids: list[str] | None,
    ) -> ChatAskResponse:
        """
        Function: Run non-streaming RAG answer pipeline.
        Params:
        - db: SQLAlchemy session.
        - query: User input query.
        - session_id: Existing chat session id.
        - collection_ids: Selected collection scope.
        Returns:
        - ChatAskResponse: Answer payload with metadata.
        """
        started = time.perf_counter()
        stages: dict[str, int] = {}

        stage_started = time.perf_counter()
        normalized_query = self._normalize_query(query)
        scope_ids = self._resolve_scope_item_ids(db, collection_ids)
        has_data = bool(scope_ids)
        route = self._route(normalized_query, has_data)
        stages["route"] = int((time.perf_counter() - stage_started) * 1000)

        merged_hits: list[dict] = []
        context = ""
        weak_context = False

        if route == "db_list":
            stage_started = time.perf_counter()
            context = self._truncate_context(self._db_list_context(db, scope_ids))
            stages["build_context"] = int((time.perf_counter() - stage_started) * 1000)
            if not context:
                route = "direct"

        if route == "db_content":
            stage_started = time.perf_counter()
            context = self._truncate_context(self._db_content_context(db, scope_ids))
            stages["build_context"] = int((time.perf_counter() - stage_started) * 1000)
            if not context:
                route = "direct"

        if route == "vector":
            stage_started = time.perf_counter()
            dense_hits = self._dense_retrieve(normalized_query, scope_ids)
            stages["dense"] = int((time.perf_counter() - stage_started) * 1000)

            stage_started = time.perf_counter()
            fts_hits = self._fts_retrieve(db, normalized_query, scope_ids)
            stages["fts"] = int((time.perf_counter() - stage_started) * 1000)

            stage_started = time.perf_counter()
            merged_hits = self._rrf_fuse(dense_hits, fts_hits)
            if not merged_hits:
                weak_context = True
                context = self._truncate_context(self._db_content_context(db, scope_ids)[:1500])
                route = "db_content" if context else "direct"
            else:
                context = self._truncate_context(
                    "\n\n".join(
                        [f"[chunk:{hit['chunk_id']}] {hit['text']}" for hit in merged_hits[: settings.rag_context_count]]
                    )
                )
            stages["build_context"] = int((time.perf_counter() - stage_started) * 1000)

        stage_started = time.perf_counter()
        history_context = self._history_context(db, session_id)
        stages["history"] = int((time.perf_counter() - stage_started) * 1000)

        stage_started = time.perf_counter()
        answer = self._build_answer(route, normalized_query, context, history_context)
        stages["llm_generate"] = int((time.perf_counter() - stage_started) * 1000)

        effective_context_len = len(re.sub(r"\s+", "", context))
        if weak_context or (route == "vector" and (len(merged_hits) <= 1 or effective_context_len < 400)):
            note = "当前资料较少，结论仅供参考，建议补充相关视频后再问一次。"
            if note not in answer:
                answer = f"{answer.rstrip()}\n\n{note}".strip()

        latency_ms = int((time.perf_counter() - started) * 1000)

        stage_started = time.perf_counter()
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
                route_type=route,
                retrieved_video_ids=sorted({hit["platform_item_id"] for hit in merged_hits}) if merged_hits else [],
                retrieved_chunk_ids=[hit["chunk_id"] for hit in merged_hits] if merged_hits else [],
                model=settings.qwen_chat_model,
            )
        )
        db.add(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content=answer,
                route_type=route,
                retrieved_video_ids=sorted({hit["platform_item_id"] for hit in merged_hits}) if merged_hits else [],
                retrieved_chunk_ids=[hit["chunk_id"] for hit in merged_hits] if merged_hits else [],
                model=settings.qwen_chat_model,
                latency_ms=latency_ms,
            )
        )
        db.commit()
        stages["db_commit"] = int((time.perf_counter() - stage_started) * 1000)

        self._log_timing("chat.ask", route, latency_ms, len(scope_ids), len(merged_hits), stages)

        return ChatAskResponse(
            session_id=session.id,
            route_type=route,
            answer=answer,
            latency_ms=latency_ms,
            hits=[
                ChatHit(
                    chunk_id=hit["chunk_id"],
                    platform_item_id=hit["platform_item_id"],
                    title=hit.get("title", ""),
                    score=round(hit["score"], 6),
                    text=hit.get("text", ""),
                )
                for hit in merged_hits
            ],
        )
    def answer_stream(
        self,
        db: Session,
        query: str,
        session_id: int | None,
        collection_ids: list[str] | None,
    ) -> Iterable[tuple[str, dict]]:
        """
        Function: Run streaming RAG pipeline and yield SSE events.
        Params:
        - db: SQLAlchemy session.
        - query: User query.
        - session_id: Existing session id.
        - collection_ids: Selected collection scope.
        Returns:
        - Iterable[tuple[str, dict]]: Event name and payload chunks.
        """
        started = time.perf_counter()
        stages: dict[str, int] = {}
        stage_started = time.perf_counter()
        normalized_query = self._normalize_query(query)
        scope_ids = self._resolve_scope_item_ids(db, collection_ids)
        has_data = bool(scope_ids)
        route = self._route(normalized_query, has_data)
        stages["route"] = int((time.perf_counter() - stage_started) * 1000)

        merged_hits: list[dict] = []
        context = ""
        weak_context = False

        if route == "db_list":
            stage_started = time.perf_counter()
            context = self._truncate_context(self._db_list_context(db, scope_ids))
            stages["build_context"] = int((time.perf_counter() - stage_started) * 1000)
            if not context:
                route = "direct"

        if route == "db_content":
            stage_started = time.perf_counter()
            context = self._truncate_context(self._db_content_context(db, scope_ids))
            stages["build_context"] = int((time.perf_counter() - stage_started) * 1000)
            if not context:
                route = "direct"

        if route == "vector":
            stage_started = time.perf_counter()
            dense_hits = self._dense_retrieve(normalized_query, scope_ids)
            stages["dense"] = int((time.perf_counter() - stage_started) * 1000)

            stage_started = time.perf_counter()
            fts_hits = self._fts_retrieve(db, normalized_query, scope_ids)
            stages["fts"] = int((time.perf_counter() - stage_started) * 1000)

            stage_started = time.perf_counter()
            merged_hits = self._rrf_fuse(dense_hits, fts_hits)
            if not merged_hits:
                weak_context = True
                context = self._truncate_context(self._db_content_context(db, scope_ids)[:1500])
                route = "db_content" if context else "direct"
            else:
                context = self._truncate_context(
                    "\n\n".join(
                        [f"[chunk:{hit['chunk_id']}] {hit['text']}" for hit in merged_hits[: settings.rag_context_count]]
                    )
                )
            stages["build_context"] = int((time.perf_counter() - stage_started) * 1000)

        stage_started = time.perf_counter()
        history_context = self._history_context(db, session_id)
        stages["history"] = int((time.perf_counter() - stage_started) * 1000)
        system, user, is_structured = self._build_prompts(route, normalized_query, context, history_context)

        parts: list[str] = []
        stage_started = time.perf_counter()
        try:
            for delta in self._get_qwen().stream_chat(
                system_prompt=system,
                user_prompt=user,
                timeout_sec=settings.qwen_stream_timeout_sec,
            ):
                if not delta:
                    continue
                parts.append(delta)
                yield "delta", {"text": delta}
            stages["llm_generate"] = int((time.perf_counter() - stage_started) * 1000)

            answer = self._sanitize_answer_text("".join(parts), is_structured)
            effective_context_len = len(re.sub(r"\s+", "", context))
            if weak_context or (route == "vector" and (len(merged_hits) <= 1 or effective_context_len < 400)):
                note = "当前资料较少，结论仅供参考，建议补充相关视频后再问一次。"
                if note not in answer:
                    answer = f"{answer.rstrip()}\n\n{note}".strip()
                    yield "delta", {"text": "\n\n" + note}

            latency_ms = int((time.perf_counter() - started) * 1000)
            stage_started = time.perf_counter()
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
                    route_type=route,
                    retrieved_video_ids=sorted({hit["platform_item_id"] for hit in merged_hits}) if merged_hits else [],
                    retrieved_chunk_ids=[hit["chunk_id"] for hit in merged_hits] if merged_hits else [],
                    model=settings.qwen_chat_model,
                )
            )
            db.add(
                ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=answer,
                    route_type=route,
                    retrieved_video_ids=sorted({hit["platform_item_id"] for hit in merged_hits}) if merged_hits else [],
                    retrieved_chunk_ids=[hit["chunk_id"] for hit in merged_hits] if merged_hits else [],
                    model=settings.qwen_chat_model,
                    latency_ms=latency_ms,
                )
            )
            db.commit()
            stages["db_commit"] = int((time.perf_counter() - stage_started) * 1000)

            self._log_timing("chat.ask.stream", route, latency_ms, len(scope_ids), len(merged_hits), stages)

            yield "done", {"ok": True}
            yield "meta", {
                "session_id": session.id,
                "route_type": route,
                "latency_ms": latency_ms,
                "hits": [
                    ChatHit(
                        chunk_id=hit["chunk_id"],
                        platform_item_id=hit["platform_item_id"],
                        title=hit.get("title", ""),
                        score=round(hit["score"], 6),
                        text=hit.get("text", ""),
                    ).model_dump()
                    for hit in merged_hits
                ],
            }
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("chat.ask.stream failed")
            yield "error", {"message": str(exc)}
    def list_sessions(self, db: Session, limit: int = 30) -> ChatSessionsResponse:
        """
        功能：列出 RagService.list_sessions 对应的数据集合。
        参数：
        - db：输入参数。
        - limit：输入参数。
        返回值：
        - ChatSessionsResponse：函数处理结果。
        """
        rows = (
            db.query(
                ChatSession,
                func.count(ChatMessage.id).label("message_count"),
                func.max(ChatMessage.created_at).label("last_message_at"),
            )
            .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .group_by(ChatSession.id)
            .order_by(desc(func.max(ChatMessage.created_at)), desc(ChatSession.created_at))
            .limit(limit)
            .all()
        )

        items = [
            ChatSessionDTO(
                id=session.id,
                title=session.title,
                message_count=int(message_count or 0),
                last_message_at=last_message_at,
                created_at=session.created_at,
            )
            for session, message_count, last_message_at in rows
        ]
        return ChatSessionsResponse(items=items)

    def get_session_messages(self, db: Session, session_id: int) -> ChatMessagesResponse | None:
        """
        功能：获取 RagService.get_session_messages 对应的数据或对象。
        参数：
        - db：输入参数。
        - session_id：输入参数。
        返回值：
        - ChatMessagesResponse | None：函数处理结果。
        """
        session = db.get(ChatSession, session_id)
        if session is None:
            return None

        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .all()
        )

        return ChatMessagesResponse(
            session_id=session_id,
            items=[
                ChatMessageDTO(
                    id=row.id,
                    session_id=row.session_id,
                    role=row.role,
                    content=row.content,
                    route_type=row.route_type,
                    created_at=row.created_at,
                )
                for row in rows
            ],
        )

    def delete_session(self, db: Session, session_id: int) -> bool:
        """
        功能：删除 RagService.delete_session 对应的资源或记录。
        参数：
        - db：输入参数。
        - session_id：输入参数。
        返回值：
        - bool：函数处理结果。
        """
        session = db.get(ChatSession, session_id)
        if session is None:
            return False
        db.delete(session)
        db.commit()
        return True

    def clear_session_messages(self, db: Session, session_id: int) -> bool:
        """
        功能：执行 RagService.clear_session_messages 的核心业务逻辑。
        参数：
        - db：输入参数。
        - session_id：输入参数。
        返回值：
        - bool：函数处理结果。
        """
        session = db.get(ChatSession, session_id)
        if session is None:
            return False

        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete(synchronize_session=False)
        db.commit()
        return True


rag_service = RagService()
