"""산업 스냅샷 공통 부품 — 산업 특성 확인 상태(TraitView), 가치사슬 지도, 사업 구조, 산업 분류 배지.

화면 조립은 industry_lens.py(가치사슬 × 사업보고서)가 한다.
색은 '좋음/나쁨'이 아니라 '근거 유형': 초록=회사 공시, 파랑=산업 추론, 회색=미확인('위험 없음'이 아님).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

import ui
from scanner import catalog, kb, ksic
from scanner.models import CLAIM_LABEL, Claim, ClaimType, Report, RiskItem, TraitEvidence

STATUS = {  # 근거 유형 → (화면 표기, 배지 색, 차트 색)
    ClaimType.FACT: ("회사 공시로 확인", "green", "#2b8a3e"),
    ClaimType.INFERENCE: ("산업자료 추론", "blue", "#4c6ef5"),
    ClaimType.UNVERIFIED: ("미확인", "gray", "#8a8f98"),
}
TYPE_COLOR = {t: v[1] for t, v in STATUS.items()}


@dataclass
class TraitView:
    trait_id: str
    name: str
    stage: str
    status: ClaimType
    evidence: list[TraitEvidence] = field(default_factory=list)
    risks: list[RiskItem] = field(default_factory=list)   # Risk Map에 올라간 검토 영역
    kb_risks: list[dict] = field(default_factory=list)    # 지식베이스상 연결된 영역 (미확인 특성 안내용)


def trait_views(r: Report) -> list[TraitView]:
    """지식베이스의 산업 특성 전체를 기준으로, 이번 실행에서 확인된 상태를 붙인다."""
    # 한 특성에 위험이 여럿이면 같은 근거가 위험마다 복사되어 있으므로 중복 제거
    evidence: dict[str, dict[tuple, TraitEvidence]] = {}
    for k in r.risks:
        for e in k.trait_evidence:
            evidence.setdefault(e.trait_id, {})[(e.rationale, tuple(e.source_ids))] = e

    out = []
    for t in kb.traits(r.snapshot.industry_key):
        ev = list(evidence.get(t["trait_id"], {}).values())
        status = (ClaimType.FACT if any(e.claim_type == ClaimType.FACT for e in ev)
                  else ClaimType.INFERENCE if ev else ClaimType.UNVERIFIED)
        ids = {x["risk_id"] for x in t["risks"]}
        out.append(TraitView(t["trait_id"], t["name"], t.get("stage", ""), status, ev,
                             [k for k in r.risks if k.risk_id in ids], t["risks"]))
    order = list(STATUS)
    out.sort(key=lambda v: (order.index(v.status), min((k.priority for k in v.risks), default=9)))
    return out


def _src(ids: list[str]) -> str:
    return " ".join(f"`{x}`" for x in ids)


def show_claims(claims: list[Claim]):
    for c in claims:
        st.markdown(f":{TYPE_COLOR[c.claim_type]}-badge[{CLAIM_LABEL[c.claim_type]}] {c.text} {_src(c.source_ids)}")
        if c.quote and c.quote.strip() != c.text.strip():
            st.caption(f"근거 원문: “{c.quote}”")
        for f in c.flags:
            st.caption(f"⚠️ {f}")


# ---------------------------------------------------------------- 2. 가치사슬 지도
def value_chain_map(r: Report, views: list[TraitView]):
    p = catalog.profile(r.snapshot.industry_key)
    stages = p["value_chain"]
    if not kb.is_supported(r.snapshot.industry_key):
        # 지식베이스에 없는 업종: 다른 산업에 끼워 넣지 않고 KSIC 대분류 '업종 일반형' 가치사슬로 보여준다 (특성 칩 없음)
        if not stages:
            return
        tpl = kb.industry(r.snapshot.industry_key).get("template", "업종 일반형")
        ui.section(f"가치사슬 — {tpl}", "업종코드(KSIC) 대분류로 고른 일반 템플릿 · 이 회사 고유 단계는 사업보고서에서 확인")
        note = "<span>업종 일반형 템플릿 — 산업 지식베이스 검토 전</span>"
        if r.snapshot.value_chain and r.snapshot.value_chain != stages:
            note += "<span>· AI가 이 회사 공시로 정리한 가치사슬: " + " → ".join(ui._h(x) for x in r.snapshot.value_chain) + "</span>"
        ui.chain(stages, p["stage_info"], {}, note)
        return
    chips: dict[str, list[str]] = {}
    for v in views:
        prio = min((k.priority for k in v.risks), default=None)
        chips.setdefault(v.stage, []).append(ui.chip(v.name, ui.STATUS_CLASS[v.status.value], prio))
    ui.section(f"가치사슬로 보는 {p['name']}", "단계마다 무슨 일·돈의 흐름·장부, 그리고 이 회사 자료로 확인한 산업 특성")
    ui.chain(stages, p["stage_info"], chips, ui.STATUS_LEGEND)
    notes = []
    orphan = [v.name for v in views if v.stage not in stages]
    if orphan:
        notes.append("단계 미지정 특성: " + ", ".join(orphan))
    if r.snapshot.value_chain and r.snapshot.value_chain != stages:
        notes.append("AI가 회사 자료로 정리한 가치사슬: " + " → ".join(r.snapshot.value_chain))
    for n in notes:
        st.caption(n)


# ---------------------------------------------------------------- 4. 사업 구조
def business_structure(r: Report):
    s = r.snapshot
    ui.section("사업 구조", "회사 공시로 확인한 내용과 산업 일반 구조를 나란히")
    c1, c2 = st.columns(2, gap="medium")
    with c1.container(border=True, height="stretch"):
        st.markdown("**회사 공시에서 확인한 내용**")
        facts = [c for c in s.business_model if c.claim_type == ClaimType.FACT]
        if facts:
            show_claims(facts)
        else:
            st.caption("공시 원문에서 인용한 사업 구조 문장이 없습니다.")
    with c2.container(border=True, height="stretch"):
        st.markdown("**이 산업의 일반적인 구조**")
        show_claims([c for c in s.business_model if c.claim_type != ClaimType.FACT])

    with st.container(border=True):
        st.markdown("**주요 이해관계자**")
        with st.container(horizontal=True, gap="small"):
            for c in s.stakeholders:
                st.badge(c.text, color=TYPE_COLOR[c.claim_type], help=CLAIM_LABEL[c.claim_type])


def classification_badges(induty_code: str, industry_key: str | None) -> str:
    """업종코드 → KSIC 이름 · 지식베이스 산업을 한 줄 배지로."""
    parts = [f":gray-badge[{ksic.label(induty_code)}]"]
    if industry_key and kb.is_supported(industry_key):
        parts.append(f":green-badge[지식베이스: {kb.industries()[industry_key]['name']}]")
    else:
        rel = kb.related_industry(induty_code)
        parts.append(":orange-badge[지식베이스 미지원 업종]"
                     + (f" :gray-badge[같은 중분류 참고: {kb.industries()[rel]['name']}]" if rel else ""))
    return " ".join(parts)


def classification_preview(induty_code: str, override: str = "자동"):
    """분석 전에 '이 회사가 어느 산업으로 분류될지'를 보여준다 (DART 기업개황 업종코드 기준)."""
    key = override if override and override != "자동" else (
        kb.industry_from_ksic(induty_code or "") or kb.unsupported_key(induty_code))
    st.markdown("산업 분류 " + classification_badges(induty_code, key))
    if override and override != "자동":
        st.caption("사이드바에서 산업을 직접 지정했습니다. 업종코드 판별 대신 지정한 산업으로 분석합니다.")
    elif not kb.is_supported(key):
        st.caption("지식베이스에 없는 업종은 다른 산업에 끼워 맞추지 않고, 감사기준상 공통 영역과 회사 공시만으로 분석합니다.")
