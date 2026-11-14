"""AI 역할 제한 — AI 출력이 리포트에 들어가기 전에 반드시 통과하는 검사.

  G1 출처 존재성: 인용한 ID가 실제 수집·정제된 청크인지
  G2 사실(FACT) 요건: 회사 원자료를 인용하고, 근거 문장(quote)이 원문에 글자 그대로 있어야 하며,
     주장의 수치는 그 근거 문장 안에 있어야 함
  G3 근거 대응도: 주장과 근거 문장의 어휘 겹침이 낮으면 '원문 대조 필요' 표시
  G4 단정 표현 차단: 위험 결론·감사의견·회계처리 적정성 판단 표현 탐지
  G5 통제 어휘: 산업 특성 ID는 지식베이스에 있는 것만 허용

가드레일은 내용을 '고쳐 쓰지' 않는다. 강등(FACT→INFERENCE→UNVERIFIED)하거나
경고 플래그를 붙여 감사인이 보도록 할 뿐이다.
"""
from __future__ import annotations

import re

from .models import AuditQuestion, Chunk, Claim, ClaimType, GuardrailEvent, TraitEvidence

KB_SOURCE_ID = "KB"

CONCLUSIVE_PATTERNS = [
    r"위험(하다|합니다|한 (회사|기업)이다)",
    r"분식",
    r"부정(을|이)\s*(저질|저지르|했)",
    r"(부적정|적정)(하다|합니다|하게 처리(되었|했))",
    r"감사의견",
    r"(한정|부적정)\s*의견|의견\s*거절",
    r"왜곡표시(가|이)\s*(있다|있습니다|존재한다|존재합니다)",
    r"오류가\s*(있다|있습니다|확인된다|확인됩니다)",
    r"(감사증거|증거)(가|는)\s*충분(하다|합니다)",
    r"문제가\s*(있다|있습니다)",
]
_CONCLUSIVE = [re.compile(p) for p in CONCLUSIVE_PATTERNS]
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
OVERLAP_THRESHOLD = 0.35


def _compact(s: str) -> str:
    """공백 차이(줄바꿈·띄어쓰기)는 무시하고 글자 그대로 비교하기 위한 정규화."""
    return re.sub(r"\s+", "", s or "")


class Guard:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = {c.chunk_id: c for c in chunks}
        self.events: list[GuardrailEvent] = []

    def _log(self, stage: str, action: str, detail: str):
        self.events.append(GuardrailEvent(stage=stage, action=action, detail=detail[:300]))

    # ---- G4 ----
    def conclusive_hits(self, text: str) -> list[str]:
        return [m.group(0) for p in _CONCLUSIVE if (m := p.search(text))]

    # ---- G1 ----
    def _valid_ids(self, ids: list[str], stage: str, text: str) -> list[str]:
        ok = [i for i in ids if i in self.chunks or i == KB_SOURCE_ID]
        bad = [i for i in ids if i not in ok]
        if bad:
            self._log(stage, "존재하지 않는 출처 제거", f"{bad} ← '{text}'")
        return ok

    # ---- G3 ----
    @staticmethod
    def overlap(text: str, source: str) -> float:
        toks = set(_TOKEN.findall(text))
        if not toks:
            return 0.0
        return sum(1 for t in toks if t in source) / len(toks)

    @staticmethod
    def numbers_supported(text: str, source: str) -> bool:
        # 부분 문자열이 아닌 '수치 단위'로 비교 ("5"가 "2,450" 안에 있다고 통과시키지 않음)
        src = {n.replace(",", "") for n in _NUM.findall(source)}
        return all(n.replace(",", "") in src for n in _NUM.findall(text))

    def _grade(self, stage: str, text: str, claim_type: ClaimType,
               ids: list[str], quote: str = "") -> tuple[ClaimType, list[str], list[str]]:
        flags: list[str] = []
        ids = self._valid_ids(ids, stage, text)
        company = [i for i in ids if i in self.chunks and self.chunks[i].scope == "company"]

        if claim_type == ClaimType.FACT:
            if not company:
                new = ClaimType.INFERENCE if ids else ClaimType.UNVERIFIED
                self._log(stage, f"FACT→{new.value} 강등", f"회사 원자료 인용 없음: '{text}'")
                flags.append("회사 원자료 근거 없음 — 사실로 표시하지 않음")
                claim_type = new
            else:
                joined = " ".join(self.chunks[i].text for i in company)
                if not quote.strip():
                    self._log(stage, "FACT→INFERENCE 강등", f"근거 문장 없음: '{text}'")
                    flags.append("근거 문장(인용) 없음 — 사실로 표시하지 않음")
                    claim_type = ClaimType.INFERENCE
                elif _compact(quote) not in _compact(joined):
                    self._log(stage, "FACT→UNVERIFIED 강등", f"인용문이 원문에 없음: '{quote[:80]}'")
                    flags.append("인용문이 원문에 없음 — 원문 대조 필요")
                    claim_type = ClaimType.UNVERIFIED
                elif not self.numbers_supported(text, quote):
                    self._log(stage, "FACT→UNVERIFIED 강등", f"근거 문장에 없는 수치: '{text}'")
                    flags.append("근거 문장에 없는 수치 포함 — 원문 대조 필요")
                    claim_type = ClaimType.UNVERIFIED
                elif self.overlap(text, quote) < OVERLAP_THRESHOLD:
                    self._log(stage, "근거 대응도 낮음 표시", f"'{text}'")
                    flags.append("근거 문장과 표현 대응도 낮음 — 원문 대조 필요")

        if claim_type == ClaimType.INFERENCE and not ids:
            self._log(stage, "INFERENCE→UNVERIFIED 강등", f"출처 없음: '{text}'")
            flags.append("출처 없는 추론")
            claim_type = ClaimType.UNVERIFIED

        hits = self.conclusive_hits(text)
        if hits:
            self._log(stage, "단정 표현 탐지", f"{hits} ← '{text}'")
            flags.append(f"단정 표현 포함({', '.join(hits)}) — AI는 결론을 내릴 수 없음")
        return claim_type, ids, flags

    # ---- 공개 API ----
    def claim(self, c: Claim, stage: str) -> Claim:
        t, ids, flags = self._grade(stage, c.text, c.claim_type, c.source_ids, c.quote)
        return c.model_copy(update={"claim_type": t, "source_ids": ids, "flags": c.flags + flags})

    def trait(self, t: TraitEvidence, allowed: set[str], stage: str) -> TraitEvidence | None:
        if t.trait_id not in allowed:  # G5
            self._log(stage, "통제 어휘 밖 특성 거부", t.trait_id)
            return None
        ct, ids, flags = self._grade(stage, t.rationale, t.claim_type, t.source_ids, t.quote)
        return t.model_copy(update={"claim_type": ct, "source_ids": ids, "flags": t.flags + flags})

    def question(self, q: AuditQuestion, stage: str) -> AuditQuestion | None:
        hits = self.conclusive_hits(q.question)
        if hits:
            self._log(stage, "단정 표현 질문 제외", f"{hits} ← '{q.question}'")
            return None
        ids = self._valid_ids(q.source_ids, stage, q.question)
        return q.model_copy(update={"source_ids": ids})
