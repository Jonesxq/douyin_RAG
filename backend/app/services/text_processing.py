from __future__ import annotations

"""文本清洗与切块工具。"""

import re
from dataclasses import dataclass


@dataclass
class RawSegment:
    text: str
    start_ms: int
    end_ms: int
    lang: str


@dataclass
class ChunkResult:
    text: str
    token_count: int
    start_ms: int
    end_ms: int
    lang: str


def clean_text(text: str) -> str:
    """
    功能：执行 clean_text 的核心业务逻辑。
    参数：
    - text：输入参数。
    返回值：
    - str：函数处理结果。
    """
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(啊|嗯|呃){2,}", "", text)
    return text.strip()


def approx_token_count(text: str) -> int:
    """
    功能：执行 approx_token_count 的核心业务逻辑。
    参数：
    - text：输入参数。
    返回值：
    - int：函数处理结果。
    """
    if not text:
        return 0
    # Lightweight token estimation for CJK + Latin mixed text.
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(text) - cjk
    return cjk + max(1, latin // 4)


def build_chunks(segments: list[RawSegment], max_tokens: int = 220) -> list[ChunkResult]:
    """
    功能：执行 build_chunks 的核心业务逻辑。
    参数：
    - segments：输入参数。
    - max_tokens：输入参数。
    返回值：
    - list[ChunkResult]：函数处理结果。
    """
    chunks: list[ChunkResult] = []
    if not segments:
        return chunks

    bucket_text: list[str] = []
    bucket_start = segments[0].start_ms
    bucket_end = segments[0].end_ms
    bucket_lang = segments[0].lang

    for seg in segments:
        cleaned = clean_text(seg.text)
        if not cleaned:
            continue

        candidate = " ".join(bucket_text + [cleaned]) if bucket_text else cleaned
        token_count = approx_token_count(candidate)

        if bucket_text and token_count > max_tokens:
            current_text = " ".join(bucket_text)
            chunks.append(
                ChunkResult(
                    text=current_text,
                    token_count=approx_token_count(current_text),
                    start_ms=bucket_start,
                    end_ms=bucket_end,
                    lang=bucket_lang,
                )
            )
            bucket_text = [cleaned]
            bucket_start = seg.start_ms
            bucket_end = seg.end_ms
            bucket_lang = seg.lang
        else:
            bucket_text.append(cleaned)
            bucket_end = seg.end_ms

    if bucket_text:
        final_text = " ".join(bucket_text)
        chunks.append(
            ChunkResult(
                text=final_text,
                token_count=approx_token_count(final_text),
                start_ms=bucket_start,
                end_ms=bucket_end,
                lang=bucket_lang,
            )
        )

    return chunks
