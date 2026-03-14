from __future__ import annotations

from typing import Sequence

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.config import get_settings

settings = get_settings()


class QwenClient:
    def __init__(self) -> None:
        if not settings.qwen_api_key:
            raise RuntimeError("QWEN_API_KEY is missing. Set it in backend/.env")

        self.client = OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=settings.qwen_embedding_model,
            input=list(texts),
        )
        return [item.embedding for item in response.data]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=settings.qwen_chat_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
