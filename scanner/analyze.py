"""3단계 — 산업 분석.

분석기는 외부 AI 없이 동작한다 (API 키 불필요).
  - 회사 공시(사업의 내용)에서 산업 특성 키워드가 들어간 '완결된 서술문'을 그대로 뽑아 근거로 쓴다
    → 원문 그대로라 수치·내용을 지어내지 않는다
  - 사업 구조·가치사슬·이해관계자 설명은 사람이 검토한 산업 지식베이스에서 가져온다
  - 그 문장이 특성의 근거인지(관련성)는 감사인이 확인하도록 표시한다

할 수 없는 것: 위험 결론, 감사의견, 회계처리 적정성 판단, 감사증거 충분성 판단
"""
from __future__ import annotations

import re

from . import kb
from .guardrails import KB_SOURCE_ID
from .models import AuditQuestion, Chunk, Claim, ClaimType, RiskItem, Snapshot, TraitEvidence


def _sentences_with(chunks: list[Chunk], words: list[str], limit: int) -> list[tuple[str, str]]:
    """회사 청크에서 키워드를 포함한 원문 문장을 그대로 추출 (추출형 = 환각 없음)."""
    out: list[tuple[str, str]] = []
    for c in chunks:
        if c.scope != "company":
            continue
        for s in re.split(r"(?<=[.?!])\s+|\n", c.text):
            s = s.strip()
            # 완결된 서술문만 근거로 쓴다. 표 제목("3) 생산능력, 생산실적 및 가동률")이나
            # 표 칸 조각("DRAM, NAND Flash, 모바일AP 등")은 키워드가 맞아도 근거가 되지 못한다.
            if not re.search(r"(다|니다)\.?$", s):
                continue
            if any(w in s for w in words) and 25 <= len(s) <= 220:
                out.append((s.strip(), c.chunk_id))
                if len(out) >= limit:
                    return out
    return out


def _gap_claims(industry_key: str, detected: set[str]) -> list[Claim]:
    return [Claim(text=f"현재 확보한 자료만으로는 '{t['name']}' 특성의 해당 여부를 확인할 수 없음",
                  claim_type=ClaimType.UNVERIFIED)
            for t in kb.traits(industry_key) if t["trait_id"] not in detected]


def _unsupported_gap(industry_key: str) -> list[Claim]:
    if kb.is_supported(industry_key):
        return []
    return [Claim(text="이 업종은 산업 지식베이스에 없어 가치사슬·산업 특성을 제시하지 않았습니다. "
                       "공시 원문(사업의 내용)을 직접 읽어 사업 구조를 확인하세요.",
                  claim_type=ClaimType.UNVERIFIED)]


# =====================================================================
class OfflineAnalyzer:
    mode = "OFFLINE"
    model = ""

    def analyze(self, industry_key: str, chunks: list[Chunk]) -> tuple[Snapshot, list[TraitEvidence]]:
        ind = kb.industry(industry_key)
        prof = ind["profile"]

        traits: list[TraitEvidence] = []
        for t in ind["traits"]:
            hits = _sentences_with(chunks, t["detect_keywords"], 2)
            if hits:
                # 문장은 원문 그대로라 '사실'이지만, 그 문장이 이 특성을 뒷받침하는지는 키워드만으로 알 수 없다.
                # (실제 공시에서 '해외 지역총괄' 문장이 외화환산 근거로 잡히는 등) → 관련성 확인을 감사인에게 넘긴다.
                traits.append(TraitEvidence(
                    trait_id=t["trait_id"], claim_type=ClaimType.FACT,
                    rationale=hits[0][0], quote=hits[0][0], source_ids=list(dict.fromkeys(cid for _, cid in hits)),
                    flags=["키워드 일치로 찾은 문장 — 이 특성의 근거인지는 감사인 확인 필요 (오프라인 모드)"]))
                continue
            ind_hits = [c.chunk_id for c in chunks if c.scope == "industry"
                        and any(w in c.text for w in t["detect_keywords"])]
            if ind_hits:
                traits.append(TraitEvidence(
                    trait_id=t["trait_id"], claim_type=ClaimType.INFERENCE,
                    rationale=f"산업자료에서 '{t['name']}' 관련 내용이 확인됨 (회사 공시로는 미확인)",
                    source_ids=ind_hits[:2]))

        facts = _sentences_with(chunks, ind["detect_keywords"], 3)
        snapshot = Snapshot(
            industry_key=industry_key, industry_name=ind["name"],
            business_model=[Claim(text=s, claim_type=ClaimType.FACT, source_ids=[cid], quote=s) for s, cid in facts]
            + [Claim(text=b, claim_type=ClaimType.INFERENCE, source_ids=[KB_SOURCE_ID])
               for b in prof["business_model"]],
            value_chain=prof["value_chain"],
            stakeholders=[Claim(text=s, claim_type=ClaimType.INFERENCE, source_ids=[KB_SOURCE_ID])
                          for s in prof["stakeholders"]],
            characteristics=[Claim(text=f"{kb_t['name']}: {t.rationale}", claim_type=t.claim_type,
                                   source_ids=t.source_ids, quote=t.quote)
                             for t in traits for kb_t in ind["traits"] if kb_t["trait_id"] == t.trait_id],
            information_gaps=_gap_claims(industry_key, {t.trait_id for t in traits}) + _unsupported_gap(industry_key),
        )
        return snapshot, traits

    def questions(self, risks: list[RiskItem], chunks: list[Chunk]) -> list[tuple[str, AuditQuestion]]:
        return []  # 오프라인 모드는 지식베이스 질문만 사용

    def extract_rpt(self, text: str) -> list[dict] | None:
        return None  # 특수관계자 표 자동 추출은 하지 않는다 → 화면에 '원문 직접 확인' 표시


# =====================================================================
