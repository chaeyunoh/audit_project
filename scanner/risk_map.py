"""4단계 — 감사 Risk Mapping (결정적 로직, AI 미사용).

산업 특성(trait) → 잠재적 위험 → 계정과목 → 경영진 주장 → 기본 확인 질문
연결은 지식베이스에서만 가져온다. AI가 정하는 것은 '어떤 특성이 해당하는가'의 후보뿐이다.

검토 우선순위(제안)
  - 회사 공시(FACT)로 특성이 확인되면 지식베이스의 기본 우선순위를 그대로 적용
  - 산업자료·추론으로만 뒷받침되면 한 단계 낮춤
  - 이는 감사인의 위험평가가 아니라 '어디부터 읽을지'에 대한 제안이다
"""
from __future__ import annotations

from . import kb
from .models import AuditQuestion, ClaimType, RiskItem, TraitEvidence


def _risk(r: dict, trait: str, priority: int, basis: str, ev: list[TraitEvidence]) -> RiskItem:
    return RiskItem(
        risk_id=r["risk_id"], title=r["title"], trait=trait, potential_risk=r["potential_risk"],
        accounts=r["accounts"], assertions=r["assertions"], references=r["references"],
        evidence_docs=r["evidence_docs"], priority=priority, basis=basis, trait_evidence=ev,
        questions=[AuditQuestion(question=q, origin="KB") for q in r["questions"]],
    )


def map_risks(industry_key: str, detected: list[TraitEvidence]) -> list[RiskItem]:
    by_trait: dict[str, list[TraitEvidence]] = {}
    for t in detected:
        if t.claim_type != ClaimType.UNVERIFIED:
            by_trait.setdefault(t.trait_id, []).append(t)

    items: list[RiskItem] = []
    for t in kb.traits(industry_key):
        ev = by_trait.get(t["trait_id"])
        if not ev:
            continue
        confirmed = any(e.claim_type == ClaimType.FACT for e in ev)
        for r in t["risks"]:
            prio = r["priority"] if confirmed else min(3, r["priority"] + 1)
            basis = "회사 공시로 확인된 특성" if confirmed else "산업 일반 특성"
            items.append(_risk(r, t["name"], prio, basis, ev))

    for r in kb.baseline_risks():
        items.append(_risk(r, r["trait"], r["priority"], "감사기준상 상시 고려", []))

    items.sort(key=lambda x: (x.priority, x.basis != "회사 공시로 확인된 특성"))
    return items
