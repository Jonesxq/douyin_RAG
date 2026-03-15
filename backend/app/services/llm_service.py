from __future__ import annotations

"""大模型客户端封装：聊天、向量化、路由分类。"""

import logging
import re
import time
from typing import Iterable, Sequence

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_local_embedder = None


def _get_local_embedder():
    """
    功能：执行 _get_local_embedder 的内部处理逻辑。
    参数：
    - 无。
    返回值：
    - 未显式标注：请以函数实现中的 return 语句为准。
    """
    global _local_embedder
    if _local_embedder is None:
        from fastembed import TextEmbedding

        _local_embedder = TextEmbedding(
            model_name=settings.local_embedding_model,
            cache_dir=settings.local_embedding_cache_dir,
        )
    return _local_embedder


class QwenClient:
    def __init__(self) -> None:
        """
        功能：初始化 QwenClient 的实例状态。
        参数：
        - 无。
        返回值：
        - None：构造函数不返回业务值。
        """
        self.client: OpenAI | None = None
        if settings.qwen_api_key:
            self.client = OpenAI(
                api_key=settings.qwen_api_key,
                base_url=settings.qwen_base_url,
                max_retries=settings.qwen_max_retries,
            )

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """
        功能：执行 QwenClient.embed_texts 的核心业务逻辑。
        参数：
        - texts：输入参数。
        返回值：
        - list[list[float]]：函数处理结果。
        """
        if not texts:
            return []

        if settings.embedding_provider.lower() == "local":
            embedder = _get_local_embedder()
            vectors = embedder.embed(list(texts))
            return [vec.tolist() for vec in vectors]

        if self.client is None:
            raise RuntimeError("QWEN_API_KEY is missing. Set it in backend/.env")

        response = self.client.embeddings.create(
            model=settings.qwen_embedding_model,
            input=list(texts),
        )
        return [item.embedding for item in response.data]

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        timeout_sec: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        功能：执行 QwenClient.chat 的核心业务逻辑。
        参数：
        - system_prompt：输入参数。
        - user_prompt：输入参数。
        - temperature：输入参数。
        - timeout_sec：输入参数。
        - max_tokens：输入参数。
        返回值：
        - str：函数处理结果。
        """
        if self.client is None:
            raise RuntimeError("QWEN_API_KEY is missing. Set it in backend/.env")

        timeout_value = timeout_sec if timeout_sec is not None else settings.qwen_chat_timeout_sec
        kwargs: dict = {
            "model": settings.qwen_chat_model,
            "temperature": temperature,
            "timeout": timeout_value,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        started = time.perf_counter()
        response = self.client.chat.completions.create(**kwargs)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("LLM chat completed in %sms (model=%s)", elapsed_ms, settings.qwen_chat_model)
        return response.choices[0].message.content or ""

    def stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        timeout_sec: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterable[str]:
        """
        功能：执行 QwenClient.stream_chat 的核心业务逻辑。
        参数：
        - system_prompt：输入参数。
        - user_prompt：输入参数。
        - temperature：输入参数。
        - timeout_sec：输入参数。
        - max_tokens：输入参数。
        返回值：
        - Iterable[str]：函数处理结果。
        """
        if self.client is None:
            raise RuntimeError("QWEN_API_KEY is missing. Set it in backend/.env")

        timeout_value = timeout_sec if timeout_sec is not None else settings.qwen_stream_timeout_sec
        kwargs: dict = {
            "model": settings.qwen_chat_model,
            "temperature": temperature,
            "stream": True,
            "timeout": timeout_value,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        started = time.perf_counter()
        stream = self.client.chat.completions.create(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("LLM stream completed in %sms (model=%s)", elapsed_ms, settings.qwen_chat_model)

    def classify_route(self, query: str) -> str | None:
        """
        功能：执行 QwenClient.classify_route 的核心业务逻辑。
        参数：
        - query：输入参数。
        返回值：
        - str | None：函数处理结果。
        """
        if not settings.rag_route_with_llm or self.client is None:
            return None

        prompt = (
            "You are a route classifier. Output only one token from: direct, db_list, db_content, vector.\n"
            "direct: greeting/casual chat not asking about favorites knowledge.\n"
            "db_list: asks for list/catalog/what videos available.\n"
            "db_content: asks overview/summary of all favorites content.\n"
            "vector: topic question requiring semantic retrieval."
        )

        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=settings.qwen_chat_model,
                temperature=0,
                timeout=settings.qwen_route_timeout_sec,
                max_tokens=settings.qwen_route_max_tokens,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": query},
                ],
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM route classify failed: %s", exc)
            return None
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("LLM route classify took %sms", elapsed_ms)

        match = re.search(r"\b(direct|db_list|db_content|vector)\b", raw)
        if not match:
            return None
        return match.group(1)
