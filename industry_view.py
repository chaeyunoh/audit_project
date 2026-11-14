"""산업 이해 화면의 공통 부품 — 지식베이스만으로 그린다 (회사 자료 없이도 동작).

색 규칙
  - 산업 일반(지식베이스) 내용: 보라 배지
  - 회사에 적용한 결과(① Snapshot): 초록=회사 공시 / 파랑=산업 추론 / 회색=미확인
  - 🔴🟠🟡: 검토 우선순위 '제안' (위험평가 결과가 아님)
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import ui
from scanner import catalog, kb
from scanner.brief import PRIORITY_ICON

KB_COLOR = "violet"
PRIO_COLOR = {1: "#c92a2a", 2: "#e8710a", 3: "#f2c94c"}


def industry_picker(label: str = "산업") -> str:
    """선택한 산업을 페이지 간에 유지한다 (session_state['industry'])."""
    keys = list(kb.industries())
    cur = st.session_state.get("industry", "construction")
    keys.sort(key=lambda k: kb.industries()[k].get("group", ""))
    def name(k: str) -> str:
        v = kb.industries()[k]
        return f"{v.get('group', '')} · {v['name']}" + (" (초안)" if v.get("review", {}).get("status") == "draft" else "")
    sel = st.selectbox(label, keys, index=keys.index(cur) if cur in keys else 0, format_func=name)
    st.session_state.industry = sel or cur
    return st.session_state.industry


def top_priority(trait: dict) -> int:
    return min(r["priority"] for r in trait["risks"])


def kb_chain_map(key: str):
    """일러스트 가치사슬 — 단계마다 무슨 일·돈의 흐름·장부, 그리고 그 단계의 산업 특성(점 색 = 우선순위)."""
    p = catalog.profile(key)
    chips: dict[str, list[str]] = {}
    for t in p["traits"]:
        chips.setdefault(t.get("stage", ""), []).append(ui.chip(t["name"], "", top_priority(t)))
    ui.chain(p["value_chain"], p["stage_info"], chips, ui.PRIO_LEGEND)


def trait_explainer(trait: dict):
    """특성 → 왜 중요한가 → 계정·주장 → 지표 → 질문·자료."""
    with st.container(border=True, height="stretch"):
        st.markdown(f"**{trait['name']}**  \n:gray-badge[{trait.get('stage', '단계 미지정')}]")
        for r in trait["risks"]:
            st.markdown(f"{PRIORITY_ICON[r['priority']]} **{r['title']}**")
            st.markdown(r["potential_risk"])
            st.markdown(":small[계정] " + " ".join(f":{KB_COLOR}-badge[{a}]" for a in r["accounts"]))
            st.markdown(":small[경영진 주장] " + " ".join(f":gray-badge[{a}]" for a in r["assertions"]))
            for m in r.get("metrics", []):
                st.caption(f"📈 재무 지표: {m['name']}")
            with st.expander("감사인이 던질 질문 · 확인 자료"):
                for q in r["questions"]:
                    st.markdown(f"- {q}")
                st.caption("확인 자료: " + ", ".join(r["evidence_docs"]))
                st.caption("참고 기준: " + ", ".join(r["references"]))


def account_heatmap(key: str):
    """계정 × 경영진 주장. 칸 색 = 그 칸에 걸린 가장 높은 우선순위."""
    heatmap_from_rows(catalog.account_assertion_rows(key), "이 산업에서 계정별로 확인하게 되는 경영진 주장과 우선순위")


def heatmap_from_rows(rows: list[dict], alt_text: str):
    """rows: {'계정','경영진 주장','검토 영역','우선순위'} — 산업(지식베이스)·회사(Risk Map) 공용."""
    df = pd.DataFrame(rows)
    if df.empty:
        st.caption("표시할 계정·주장 연결이 없습니다.")
        return
    agg = (df.groupby(["계정", "경영진 주장"])
             .agg(우선순위=("우선순위", "min"), 검토영역=("검토 영역", lambda s: ", ".join(dict.fromkeys(s))))
             .reset_index())
    agg["우선순위 표시"] = agg["우선순위"].map({1: "1 우선", 2: "2 중간", 3: "3 참고"})
    order = list(catalog.assertions())
    chart = alt.Chart(agg).mark_rect(stroke="white", strokeWidth=1).encode(
        x=alt.X("경영진 주장:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("계정:N", sort=list(dict.fromkeys(df["계정"])), title=None),
        color=alt.Color("우선순위 표시:N", title="우선순위(제안)",
                        scale=alt.Scale(domain=["1 우선", "2 중간", "3 참고"], range=list(PRIO_COLOR.values())),
                        legend=alt.Legend(orient="bottom")),
        tooltip=["계정:N", "경영진 주장:N", "우선순위 표시:N", alt.Tooltip("검토영역:N", title="검토 영역")],
    ).properties(height=max(160, 26 * agg["계정"].nunique()))
    st.altair_chart(chart, alt=alt_text)


def assertion_heatmap(keys: list[str]):
    df = pd.DataFrame(catalog.assertion_matrix(keys))
    order = list(catalog.assertions())
    base = alt.Chart(df).encode(
        x=alt.X("경영진 주장:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("산업:N", title=None),
    )
    rect = base.mark_rect(stroke="white", strokeWidth=1).encode(
        color=alt.Color("검토 영역 수:Q", scale=alt.Scale(scheme="purples", domainMin=0), legend=None),
        tooltip=["산업:N", "경영진 주장:N", "검토 영역 수:Q"])
    text = base.mark_text().encode(
        text=alt.condition(alt.datum["검토 영역 수"] > 0, "검토 영역 수:Q", alt.value("")),
        color=alt.condition(alt.datum["검토 영역 수"] >= 3, alt.value("white"), alt.value("#333")))
    st.altair_chart((rect + text).properties(height=60 + 40 * len(keys)),
                    alt="산업별로 경영진 주장마다 걸린 검토 영역 수")


def assertion_glossary():
    with st.expander("경영진 주장(Assertion) 용어"):
        st.table(pd.DataFrame([{"주장": k, "뜻": v} for k, v in catalog.assertions().items()]),
                 hide_index=True, alt="경영진 주장 8가지의 뜻")
