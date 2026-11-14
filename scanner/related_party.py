"""특수관계자 거래 교차점검 (감사기준서 550).

같은 회사의 같은 사업보고서 안에서도 특수관계자 거래는 두 곳에 나온다.
  - 'X. 대주주 등과의 거래내용' (사업보고서 본문)
  - 재무제표 주석의 '특수관계자 거래'
두 기재가 서로 어긋나면 감사인이 식별 완전성을 확인해야 할 지점이다.

흐름: AI 추출(후보) → 원문 인용 검증(코드) → 교차 비교(코드)
  - AI는 표에서 거래를 '옮겨 적는' 일만 한다.
  - 인용문(quote)이 원문에 글자 그대로 없으면 버리고, 각 필드 값이 인용문 안에 없으면 버린다.
  - 비교·금액 단위 환산·불일치 판정은 전부 코드가 한다.
  - 추출이 실패하거나 실행되지 않았으면 '불일치 없음'이 아니라 '확인 필요'로 표시한다.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field

FIELDS = ("related_party", "relationship", "transaction_type", "amount")
FIELD_LABEL = {"related_party": "거래상대방", "relationship": "관계",
               "transaction_type": "거래 유형", "amount": "금액"}

Status = Literal["ok", "partial", "failed", "not_run", "no_source"]
STATUS_LABEL = {"ok": "검증 완료", "partial": "일부 항목 제외", "failed": "추출 실패 — 확인 필요",
                "not_run": "자동 추출 안 함 — 원문 직접 확인", "no_source": "원문 구간 없음 — 확인 필요"}


class RPTItem(BaseModel):
    related_party: str
    relationship: str = ""
    transaction_type: str
    amount: str = ""
    quote: str
    source_id: str


class Extraction(BaseModel):
    source_id: str | None
    label: str
    status: Status
    origin: Literal["AI", "데모 고정 응답", "-"] = "-"
    items: list[RPTItem] = Field(default_factory=list)
    dropped: list[dict] = Field(default_factory=list)   # {index, reason, detail}
    truncated: bool = False   # 원문 구간이 너무 길어 앞부분만 읽음 → '이 쪽에 없음'은 결론 낼 수 없음


class Discrepancy(BaseModel):
    issue: str
    evidence: str
    gap_won: float | None = None   # 금액 불일치일 때 두 기재의 차이(원) — 중요성 비교용


class RPTReview(BaseModel):
    business: Extraction
    notes: Extraction
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    conclusive: bool = False      # 양쪽 모두 검증 완료일 때만 '불일치 없음'을 말할 수 있음


# ---------------- 정규화 ----------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def _compact(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


_UNIT = {"원": 1, "천원": 1_000, "만원": 10_000, "백만원": 1_000_000, "억원": 100_000_000}


def amount_won(s: str, default_unit: str = "") -> Decimal | None:
    """'1,234 백만원' → 원 단위 Decimal. 단위가 없으면 표의 단위(default_unit)를 쓴다."""
    m = re.fullmatch(r"([+-]?[\d,]+(?:\.\d+)?)(천원|만원|백만원|억원|원)?", _compact(s))
    if not m:
        return None
    unit = m.group(2) or default_unit
    if unit not in _UNIT:
        return None
    try:
        return Decimal(m.group(1).replace(",", "")) * _UNIT[unit]
    except InvalidOperation:
        return None


def table_unit(text: str) -> str:
    m = re.search(r"단위\s*[:：]\s*(천원|만원|백만원|억원|원)", text)
    return m.group(1) if m else ""


# ---------------- 인용 검증 ----------------
def verify(raw_items: list[dict], source_text: str, source_id: str) -> tuple[list[RPTItem], list[dict]]:
    """인용문이 원문에 있고, 각 필드 값이 인용문 안에 있는 항목만 남긴다 (공백 차이는 허용)."""
    src = _compact(source_text)
    items, dropped = [], []
    for i, c in enumerate(raw_items):
        if not isinstance(c, dict) or any(not isinstance(c.get(f, ""), str) for f in (*FIELDS, "quote")):
            dropped.append({"index": i, "reason": "형식 오류", "detail": str(c)[:120]})
            continue
        q = c.get("quote", "").strip()
        if not c.get("related_party", "").strip() or not c.get("transaction_type", "").strip():
            dropped.append({"index": i, "reason": "필수 필드 누락", "detail": q[:120]})
            continue
        if not q or _compact(q) not in src:
            dropped.append({"index": i, "reason": "인용문이 원문에 없음", "detail": q[:120]})
            continue
        outside = [FIELD_LABEL[f] for f in FIELDS if c.get(f, "").strip() and _compact(c[f]) not in _compact(q)]
        if outside:
            dropped.append({"index": i, "reason": f"인용문 밖의 값({', '.join(outside)})", "detail": q[:120]})
            continue
        items.append(RPTItem(source_id=source_id, quote=q, **{f: c.get(f, "").strip() for f in FIELDS}))
    return items, dropped


def build_extraction(label: str, source_id: str | None, source_text: str | None,
                     raw: list[dict] | None, origin: str, truncated: bool = False) -> Extraction:
    if not source_id or not source_text:
        return Extraction(source_id=source_id, label=label, status="no_source")
    if raw is None:
        return Extraction(source_id=source_id, label=label, status="not_run")
    items, dropped = verify(raw, source_text, source_id)
    status: Status = "ok" if not dropped else ("partial" if items else "failed")
    if not raw:
        status = "ok"  # 거래 없음도 정상 응답
    return Extraction(source_id=source_id, label=label, status=status, origin=origin,
                      items=items, dropped=dropped, truncated=truncated)


# ---------------- 교차 비교 ----------------
def _desc(x: RPTItem) -> str:
    return f"[{x.source_id}] “{x.quote[:90]}”"


def cross_check(biz: Extraction, notes: Extraction, biz_unit: str = "", notes_unit: str = "") -> RPTReview:
    review = RPTReview(business=biz, notes=notes)
    if biz.status not in ("ok", "partial") or notes.status not in ("ok", "partial"):
        return review  # 한쪽이라도 없으면 비교하지 않는다 → 화면에서 '확인 필요'
    review.conclusive = biz.status == notes.status == "ok" and not (biz.truncated or notes.truncated)

    def by_party(ex: Extraction) -> dict[str, list[RPTItem]]:
        d: dict[str, list[RPTItem]] = {}
        for it in ex.items:
            d.setdefault(norm(it.related_party), []).append(it)
        return d

    b, n = by_party(biz), by_party(notes)
    for party in sorted(set(b) | set(n)):
        # 한쪽이 잘렸으면 '그쪽에 없음'은 잘린 뒷부분에 있을 수 있어 불일치로 보지 않는다 (questions()에서 확인 요청)
        if party not in n and notes.truncated:
            continue
        if party not in b and biz.truncated:
            continue
        if party not in n:
            review.discrepancies += [Discrepancy(
                issue=f"'{x.related_party}' 거래가 사업보고서에는 있으나 재무제표 주석에서 확인되지 않음",
                evidence=_desc(x)) for x in b[party]]
            continue
        if party not in b:
            review.discrepancies += [Discrepancy(
                issue=f"'{x.related_party}' 거래가 재무제표 주석에는 있으나 사업보고서 '대주주 등과의 거래'에서 확인되지 않음",
                evidence=_desc(x)) for x in n[party]]
            continue
        for x in b[party]:
            same = [y for y in n[party] if norm(y.transaction_type) == norm(x.transaction_type)]
            if not same:
                review.discrepancies.append(Discrepancy(
                    issue=f"'{x.related_party}'의 거래 유형 '{x.transaction_type}'이 주석에서 확인되지 않음",
                    evidence=f"사업보고서 {_desc(x)} / 주석 유형: {', '.join(y.transaction_type for y in n[party])}"))
                continue
            if len(same) > 1:
                review.discrepancies.append(Discrepancy(
                    issue=f"'{x.related_party}' {x.transaction_type} 거래가 주석에 여러 건 — 합계 기준 확인 필요",
                    evidence=" / ".join(_desc(y) for y in same)))
                continue
            y = same[0]
            ax, ay = amount_won(x.amount, biz_unit), amount_won(y.amount, notes_unit)
            if x.amount and y.amount and (ax is None or ay is None):
                review.discrepancies.append(Discrepancy(
                    issue=f"'{x.related_party}' {x.transaction_type} 금액의 단위를 확인할 수 없어 비교 불가",
                    evidence=f"사업보고서 '{x.amount}' / 주석 '{y.amount}'"))
            elif ax is not None and ay is not None and ax != ay:
                review.discrepancies.append(Discrepancy(
                    gap_won=float(abs(ax - ay)),
                    issue=f"'{x.related_party}' {x.transaction_type} 금액이 두 기재에서 다름",
                    evidence=f"사업보고서 {x.amount} (표 단위 {biz_unit or '-'}) {_desc(x)} / "
                             f"주석 {y.amount} (표 단위 {notes_unit or '-'}) {_desc(y)}"))
        # 관계 기재는 거래상대방 단위로 한 번만 비교
        rb = {norm(x.relationship): x for x in b[party] if x.relationship}
        rn = {norm(y.relationship): y for y in n[party] if y.relationship}
        if rb and rn and not set(rb) & set(rn):
            x, y = next(iter(rb.values())), next(iter(rn.values()))
            review.discrepancies.append(Discrepancy(
                issue=f"'{x.related_party}'의 관계 기재가 다름 ('{x.relationship}' vs '{y.relationship}')",
                evidence=f"{_desc(x)} / {_desc(y)}"))
    return review


def questions(review: RPTReview) -> list[str]:
    """불일치마다 확인 질문 1개 (템플릿, AI 미사용)."""
    qs = [f"{d.issue}. 두 기재의 차이 원인(집계 범위·기간·연결범위 차이 등)과 정확한 거래 내역은?"
          for d in review.discrepancies]
    for ex in (review.business, review.notes):
        if ex.truncated:
            qs.append(f"{ex.label} 원문이 길어 앞부분만 자동 비교했다. 뒷부분의 거래(특히 한쪽에만 있는 거래처)는 "
                      "원문에서 직접 확인해야 한다.")
        if ex.status == "partial":
            qs.append(f"{ex.label}에서 원문 대조에 실패해 자동 비교에서 제외된 항목이 {len(ex.dropped)}건 있다. "
                      "해당 행을 원문에서 직접 확인해야 한다.")
        elif ex.status not in ("ok",):
            qs.append(f"{ex.label}의 특수관계자 거래를 자동으로 확인하지 못했다({STATUS_LABEL[ex.status]}). "
                      "원문에서 거래 목록을 직접 확인해야 한다.")
    return qs
