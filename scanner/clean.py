"""2단계 — 데이터 정제.

1) 민감자료 차단: 비공개 감사자료로 의심되는 문서는 분석에서 제외 (보안 게이트)
2) 마크업 제거·공백 정규화
3) 개인정보 마스킹: AI에 전달되기 전에 수행
4) 청크 분할: 인용 단위(chunk_id)를 부여해 모든 주장이 원문 위치로 추적되게 함
"""
from __future__ import annotations

import html
import re

from .models import Chunk, CleaningReport, SourceDoc

# 비공개 감사·내부 자료로 의심되는 표지. 하나라도 있으면 문서 전체를 차단한다.
SENSITIVE_MARKERS = [
    "감사조서", "대외비", "내부용", "사내한", "기밀", "CONFIDENTIAL", "INTERNAL ONLY",
    "Strictly Private", "관리자 외 열람금지", "시산표", "총계정원장",
]

PII_PATTERNS: dict[str, re.Pattern] = {
    "주민등록번호": re.compile(r"\b\d{6}-?[1-4]\d{6}\b"),
    "이메일": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "전화번호": re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    "계좌번호": re.compile(r"\b\d{3,6}-\d{2,6}-\d{2,8}(?:-\d{1,3})?\b"),
}

CHUNK_CHARS = 500  # 작을수록 인용 위치가 정밀해진다


def is_sensitive(text: str) -> str | None:
    up = text.upper()
    for m in SENSITIVE_MARKERS:
        if m.upper() in up:
            return m
    return None


def strip_markup(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"</?(p|br|tr|div|li|title|h\d)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def mask_pii(text: str, counter: dict[str, int]) -> str:
    for label, pat in PII_PATTERNS.items():
        text, n = pat.subn(f"[{label} 마스킹]", text)
        if n:
            counter[label] = counter.get(label, 0) + n
    return text


def split_chunks(doc_id: str, text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """문장 경계를 최대한 유지하며 limit 이하로 분할."""
    sentences = re.split(r"(?<=[.?!])\s+|\n", text)
    chunks, buf = [], ""
    for s in filter(None, (x.strip() for x in sentences)):
        if len(buf) + len(s) + 1 > limit and buf:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}\n{s}".strip()  # 줄바꿈 유지: 제목과 본문 문장이 섞이지 않게
    if buf:
        chunks.append(buf)
    return chunks


def clean(docs: list[SourceDoc]) -> tuple[list[SourceDoc], list[Chunk], CleaningReport]:
    report = CleaningReport()
    kept, chunks = [], []
    for d in docs:
        # 보안 게이트는 '사용자가 올린 자료'를 위한 것이다. DART 공시는 출처상 공개 자료이므로 검사하지 않는다.
        # (공시 본문에도 '영업기밀' 같은 단어가 나와, 검사하면 삼성전자 사업의 내용 전체가 차단되는 오탐이 생겼다)
        marker = None if d.publisher.startswith("DART") else is_sensitive(d.raw_text)
        if marker:
            report.blocked_docs.append(f"{d.doc_id} {d.title} (표지: '{marker}')")
            continue
        text = mask_pii(strip_markup(d.raw_text), report.masked_items)
        kept.append(d.model_copy(update={"raw_text": text}))
        for i, c in enumerate(split_chunks(d.doc_id, text), start=1):
            chunks.append(Chunk(chunk_id=f"{d.doc_id}-{i:03d}", doc_id=d.doc_id,
                                scope=d.scope, text=c))
    report.chunk_count = len(chunks)
    return kept, chunks, report
