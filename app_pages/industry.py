"""산업 깊이 보기 — 한 산업의 사업 구조, 가치사슬, 감사상 특성을 순서대로 읽는다."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import industry_view as iv
import ui
from scanner import catalog

key = iv.industry_picker()
p = catalog.profile(key)

ui.industry_head(p)
ui.plain("감사인의 눈으로 한 문장",
         "먼저 볼 곳은 " + ", ".join(r["title"] for r in p["top_risks"]) + "입니다.",
         f"산업 특성 {len(p['traits'])}개에서 검토 영역 {len(p['risks'])}개가 나오고, "
         f"그중 {len(p['top_risks'])}개를 우선 검토로 제안합니다.")

# 1. 돈을 어떻게 버나
st.subheader("1. 이 산업은 어떻게 돈을 버나")
c1, c2 = st.columns([3, 2])
with c1.container(border=True, height="stretch"):
    st.markdown("**사업 구조**")
    for b in p["business_model"]:
        st.markdown(f"- {b}")
with c2.container(border=True, height="stretch"):
    st.markdown("**주요 이해관계자**")
    with st.container(horizontal=True, gap="small"):
        for s in p["stakeholders"]:
            st.badge(s, color=iv.KB_COLOR)

# 2. 가치사슬 — 일러스트
st.subheader("2. 가치사슬: 일이 흐르는 순서, 돈이 흐르는 방향")
st.caption("단계마다 무슨 일이 일어나고, 돈이 누구에게서 누구에게로 가며, 그 결과 장부에 무엇이 남는지 봅니다. "
           "아래 칩은 그 단계에서 감사상 주의할 산업 특성입니다. 옆으로 밀어서 모든 단계를 볼 수 있습니다.")
iv.kb_chain_map(key)

# 3. 특성별로 무엇을 보나
st.subheader("3. 특성별로 무엇을 확인하나")
st.caption("각 특성이 왜 감사상 중요한지, 어떤 계정·주장과 연결되는지, 감사인이 무엇을 물어볼지 정리했습니다. "
           "가치사슬 순서로 나열합니다.")
stage_order = {s: i for i, s in enumerate(p["value_chain"])}
traits = sorted(p["traits"], key=lambda t: (stage_order.get(t.get("stage"), 99), iv.top_priority(t)))
with st.grid(2, gap="small", min_column_width=340):
    for t in traits:
        iv.trait_explainer(t)

# 4. 계정 지도
st.subheader("4. 계정 × 경영진 주장 지도")
st.caption("이 산업에서 어떤 계정의 어떤 주장을 주로 확인하게 되는지 한 장으로 봅니다. 칸에 마우스를 올리면 검토 영역이 보입니다.")
iv.account_heatmap(key)
iv.assertion_glossary()

# 5. 재무 지표
if p["metrics"]:
    st.subheader("5. 재무제표로 먼저 볼 지표")
    st.caption("공시 재무제표만으로 계산할 수 있는 지표입니다. 기준을 넘으면 결론이 아니라 '확인할 곳'을 뜻합니다.")
    st.dataframe(pd.DataFrame(p["metrics"]), hide_index=True, alt=f"{p['name']} 재무 지표와 확인 신호 기준")

st.divider()
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption("이 산업의 실제 회사 공시로 특성을 확인해 보려면")
    if st.button(f"{p['name']} 회사에 적용", icon=":material/domain:", type="primary", key="apply_company"):
        st.session_state.industry_override = key
        st.switch_page("app_pages/company.py")
