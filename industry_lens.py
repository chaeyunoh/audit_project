"""① 가치사슬 × 사업보고서 — 기업 분석의 중심 화면.

'이 산업은 어떤 단계로 돈을 버나'(지식베이스 가치사슬)를 '이 회사 사업보고서가 실제로 무엇을 말하나'와 겹쳐 본다.
  1. 일러스트 가치사슬 (단계마다 이 회사에서 확인한 산업 특성 칩)
  2. 그래프 3개: 단계별 공시 언급량 · 단계별 검토 영역(우선순위) · 산업 특성 확인 상태
  3. 단계 탐색: 단계를 고르면 무슨 일·돈·장부 / 그 단계 산업 특성과 근거 / 사업보고서 원문 문장(키워드 강조)
  4. 사업 구조 (회사 공시 vs 산업 일반)
숫자는 모두 지식베이스·공시 원문에서 센 값이며, 새 판단을 만들지 않는다.
"""
from __future__ import annotations

import re
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

import illustrations as art
import snapshot_view as sv
import ui
from scanner import catalog, kb, ksic
from scanner.brief import PRIORITY_ICON
from scanner.models import ClaimType, Report
from scanner.report_parse import find_sentences, keyword_counts, stage_keywords

PRIO_COLOR = {1: "#C0261A", 2: "#E8710A", 3: "#E0B400"}
PRIO_NAME = {1: "우선", 2: "중간", 3: "참고"}


def _h(x) -> str:
    return escape(str(x or ""))


def highlight(sentence: str, keywords: list[str]) -> str:
    """원문 문장을 이스케이프한 뒤 키워드만 <mark>로 감싼다."""
    out = _h(sentence)
    for k in sorted(set(keywords), key=len, reverse=True):
        out = re.sub(re.escape(_h(k)), lambda m: f"<mark>{m.group(0)}</mark>", out)
    return out


def stage_frame(r: Report, views: list[sv.TraitView]) -> pd.DataFrame:
    """단계별: 공시 언급 수, 우선순위별 검토 영역 수, 대표 키워드."""
    p = catalog.profile(r.snapshot.industry_key)
    kws = stage_keywords(p["traits"], p["value_chain"], p["stage_info"])
    rows = []
    for i, s in enumerate(p["value_chain"], 1):
        c = keyword_counts(r.business_sections, kws.get(s, [])) if r.business_sections else {}
        top = [k for k, n in sorted(c.items(), key=lambda x: -x[1]) if n][:3]
        risks = [k for v in views if v.stage == s for k in v.risks]
        rows.append({"순서": i, "단계": s, "공시 언급": sum(c.values()), "대표 키워드": ", ".join(top) or "-",
                     **{f"p{n}": sum(k.priority == n for k in risks) for n in (1, 2, 3)}})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 그래프
def mention_chart(df: pd.DataFrame, company: str):
    order = list(df["단계"])
    base = alt.Chart(df).encode(y=alt.Y("단계:N", sort=order, title=None, axis=alt.Axis(labelLimit=140)))
    bar = base.mark_bar(cornerRadiusEnd=4, height=18).encode(
        x=alt.X("공시 언급:Q", title="사업보고서 언급 수", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("공시 언급:Q", scale=alt.Scale(range=["#DCEBFB", "#2F7FE0"]), legend=None),
        tooltip=["단계:N", "공시 언급:Q", "대표 키워드:N"])
    txt = base.mark_text(align="left", dx=4, fontWeight=600, color="#0B0B0C").encode(
        x="공시 언급:Q", text="공시 언급:Q")
    st.altair_chart((bar + txt).properties(height=34 * len(df) + 30),
                    alt=f"{company} 사업보고서가 가치사슬 단계별로 언급한 횟수")


def risk_stack_chart(df: pd.DataFrame):
    long = df.melt(id_vars=["순서", "단계"], value_vars=["p1", "p2", "p3"], var_name="p", value_name="검토 영역")
    long["우선순위"] = long["p"].map({"p1": "우선", "p2": "중간", "p3": "참고"})
    long = long[long["검토 영역"] > 0]
    if long.empty:
        st.caption("이 산업 특성에서 Risk Map으로 올라간 검토 영역이 없습니다.")
        return
    chart = alt.Chart(long).mark_bar(height=18).encode(
        y=alt.Y("단계:N", sort=list(df["단계"]), title=None, axis=alt.Axis(labelLimit=140)),
        x=alt.X("sum(검토 영역):Q", title="검토 영역 수", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("우선순위:N", scale=alt.Scale(domain=list(PRIO_NAME.values()), range=list(PRIO_COLOR.values())),
                        legend=alt.Legend(orient="bottom", title=None)),
        order=alt.Order("p:N"), tooltip=["단계:N", "우선순위:N", "검토 영역:Q"])
    st.altair_chart(chart.properties(height=34 * len(df) + 30), alt="가치사슬 단계별 검토 영역 수와 우선순위 제안")


def status_donut(views: list[sv.TraitView]):
    rows = [{"상태": sv.STATUS[t][0], "특성": sum(v.status == t for v in views), "색": sv.STATUS[t][2]} for t in sv.STATUS]
    df = pd.DataFrame([x for x in rows if x["특성"]])
    if df.empty:
        return
    arc = alt.Chart(df).mark_arc(innerRadius=58, outerRadius=92, cornerRadius=3, padAngle=.02).encode(
        theta="특성:Q",
        color=alt.Color("상태:N", scale=alt.Scale(domain=[x["상태"] for x in rows], range=[x["색"] for x in rows]),
                        legend=alt.Legend(orient="bottom", title=None, columns=1)),
        tooltip=["상태:N", "특성:Q"])
    n_fact = sum(v.status == ClaimType.FACT for v in views)
    center = alt.Chart(pd.DataFrame({"t": [f"{n_fact}/{len(views)}"]})).mark_text(
        fontSize=26, fontWeight=700, color="#0B0B0C").encode(text="t:N")
    sub = alt.Chart(pd.DataFrame({"t": ["공시로 확인"]})).mark_text(dy=20, fontSize=11, color="#6B6B6B").encode(text="t:N")
    st.altair_chart((arc + center + sub).properties(height=260),
                    alt=f"산업 특성 {len(views)}개 중 회사 공시로 확인 {n_fact}개")


# ---------------------------------------------------------------- 단계 탐색
def stage_card(stage: str, i: int, info: dict):
    rows = "".join(f'<div class="row"><b>{k}</b>{_h(info[f])}</div>' for k, f in (("돈", "money"), ("장부", "books"))
                   if info.get(f))
    ui.block(f'<div class="ais-stage ais-stage-lg"><div class="art">{art.img(info.get("icon", ""), 110)}</div>'
             f'<div><span class="pill">STEP {i:02d}</span></div><div class="nm">{_h(stage)}</div>'
             + (f'<div class="do">{_h(info["do"])}</div>' if info.get("do") else "") + rows + '</div>')


def stage_traits(stage_views: list[sv.TraitView]):
    if not stage_views:
        st.caption("이 단계에 연결된 산업 특성이 없습니다. 흐름 이해용 단계입니다.")
        return
    for v in stage_views:
        label, color, _ = sv.STATUS[v.status]
        with st.container(border=True):
            st.markdown(f"**{v.name}**  \n:{color}-badge[{label}]")
            for e in v.evidence[:1]:
                st.caption(f"“{(e.quote or e.rationale)[:160]}”")
            for k in v.risks:
                st.markdown(f"{PRIORITY_ICON[k.priority]} {k.title}  \n"
                            + " ".join(f":violet-badge[{a}]" for a in k.accounts[:3]))
            if v.status == ClaimType.UNVERIFIED:
                docs = list(dict.fromkeys(d for x in v.kb_risks for d in x["evidence_docs"]))
                st.caption("확인 자료: " + ", ".join(docs[:3]))


def stage_quotes(r: Report, keywords: list[str]):
    if not r.business_sections:
        st.caption("사업보고서 원문이 없습니다 (데모·업로드 자료).")
        return
    found = find_sentences(r.business_sections, keywords, limit=5)
    counts = {k: n for k, n in keyword_counts(r.business_sections, keywords).items() if n}
    if counts:
        chips = "".join(f'<span class="ais-chip inf">{_h(k)} <b>{n}</b></span>'
                        for k, n in sorted(counts.items(), key=lambda x: -x[1])[:8])
        ui.block(f'<div class="ais-kw">{chips}</div>')
    if not found:
        st.caption("이 단계의 키워드가 사업보고서 '사업의 내용'에 나오지 않습니다. "
                   "공시에서 다루지 않는 단계일 수 있으니 회사에 직접 확인하세요.")
        return
    ui.block('<div class="ais-quotes">' + "".join(
        f'<div class="q"><span class="pill gray">{_h(x["section"])}</span><div>{highlight(x["sentence"], x["hits"])}</div></div>'
        for x in found) + '</div>')


def stage_explorer(r: Report, views: list[sv.TraitView], df: pd.DataFrame):
    p = catalog.profile(r.snapshot.industry_key)
    stages = p["value_chain"]
    kws = stage_keywords(p["traits"], stages, p["stage_info"])
    busiest = df.sort_values(["공시 언급", "순서"], ascending=[False, True])["단계"].iloc[0] if len(df) else stages[0]
    pick = st.segmented_control("단계", stages, default=busiest, key="vc_stage", label_visibility="collapsed",
                                format_func=lambda s: f"{stages.index(s) + 1}. {s}") or busiest
    i = stages.index(pick) + 1
    c1, c2, c3 = st.columns([1.05, 1.5, 1.9], gap="medium")
    with c1:
        stage_card(pick, i, p["stage_info"].get(pick, {}))
    with c2:
        st.markdown("**이 단계의 산업 특성 → 검토 영역**")
        if kb.is_supported(r.snapshot.industry_key):
            stage_traits([v for v in views if v.stage == pick])
        else:
            st.caption("업종 일반형 가치사슬에는 산업 특성을 붙이지 않습니다. 오른쪽 공시 원문으로 이 단계의 실제 모습을 확인하고, "
                       "감사기준상 공통 영역은 Risk Map에서 보세요.")
    with c3:
        st.markdown("**사업보고서는 이 단계를 이렇게 말합니다**")
        stage_quotes(r, kws.get(pick, []))


# ---------------------------------------------------------------- 화면
def render(r: Report):
    s = r.snapshot
    supported = kb.is_supported(s.industry_key)
    p = catalog.profile(s.industry_key)
    if not p["value_chain"]:
        ui.plain("가치사슬", f"{r.company}의 업종코드가 없어 가치사슬을 그릴 수 없습니다.",
                 "'사업보고서 요약' 탭에서 회사가 직접 설명한 사업 구조를 확인하세요.")
        sv.business_structure(r)
        return
    if not supported:
        tpl = kb.industry(s.industry_key).get("template", "")
        ui.plain("업종 일반 가치사슬",
                 f"{r.company}의 업종({ksic.label(r.induty_code)})은 산업 지식베이스에 아직 없어 '{tpl}' 가치사슬로 읽습니다.",
                 "단계별 공시 문장은 이 회사 사업보고서 원문에서 찾았고(오프라인), 산업 특성·검토 우선순위는 붙이지 않습니다.")

    views = sv.trait_views(r)
    df = stage_frame(r, views)
    sv.value_chain_map(r, views)

    ui.section("단계별로 한눈에", "공시가 많이 말하는 단계와 감사에서 볼 단계가 같은지 비교해 보세요")
    if not supported:
        with st.container(border=True):
            st.markdown("**사업보고서 언급량**")
            st.caption("단계 이름·단계 키워드가 '사업의 내용' 본문과 표에 나온 횟수")
            if r.business_sections:
                mention_chart(df, r.company)
            else:
                st.caption("사업보고서 원문이 없습니다.")
        ui.section("단계 탐색", "단계를 고르면 무슨 일·돈·장부와 공시 원문을 나란히 봅니다")
        stage_explorer(r, views, df)
        sv.business_structure(r)
        return
    c1, c2, c3 = st.columns([1.25, 1.25, 1], gap="medium")
    with c1.container(border=True, height="stretch"):
        st.markdown("**사업보고서 언급량**")
        st.caption("단계 이름·산업 특성 키워드가 '사업의 내용' 본문과 표에 나온 횟수")
        if r.business_sections:
            mention_chart(df, r.company)
        else:
            st.caption("사업보고서 원문이 없습니다 (데모·업로드 자료).")
    with c2.container(border=True, height="stretch"):
        st.markdown("**검토 영역 · 우선순위 제안**")
        st.caption("단계에 걸린 산업 특성에서 Risk Map으로 올라간 영역")
        risk_stack_chart(df)
    with c3.container(border=True, height="stretch"):
        st.markdown("**산업 특성 확인 상태**")
        st.caption("미확인 = 위험 없음이 아니라 자료로 판단 불가")
        status_donut(views)

    ui.section("단계 탐색", "단계를 고르면 무슨 일·돈·장부와 공시 원문을 나란히 봅니다 (처음엔 공시 언급이 가장 많은 단계)")
    stage_explorer(r, views, df)

    sv.business_structure(r)
    with st.expander("전체 분석 문장 (키워드 추출 원본)"):
        sv.show_claims(s.characteristics)
        st.markdown("**정보 공백**")
        sv.show_claims(s.information_gaps)
