"""산업 목록 — 참고용. 지식베이스의 산업을 훑고 깊이 보기·기업 분석으로 이어 준다.

중심 화면은 기업 분석이다. 본부별 산업·산업 비교 화면은 보류(파일은 남겨 둠).
"""
from __future__ import annotations

import streamlit as st

import ui
from scanner import catalog, kb
from scanner.brief import PRIORITY_ICON

profiles = [catalog.profile(k) for k in kb.industries()]
refs = {ref for p in profiles for r in p["risks"] for ref in r["references"]}

ui.hero(
    "처음 맡는 산업도, 감사인의 눈으로 빠르게",
    "돈을 어떻게 버는지 → 어디서 회계 판단이 생기는지 → 무엇을 물어볼지. 산업 이해를 몇 분 안에.",
    "산업 지식베이스 한눈에", f"사람이 검토한 지식베이스 v{kb.kb_version()} · 회사 자료 없이 바로 공부할 수 있습니다",
    [("산업", str(len(profiles)), "개", "깊이 보기·비교 가능"),
     ("산업 특성", str(sum(len(p["traits"]) for p in profiles)), "개", "가치사슬 단계별 정리"),
     ("검토 영역", str(sum(len(p["risks"]) for p in profiles)), "개", f"우선 검토 {sum(len(p['top_risks']) for p in profiles)}개"),
     ("기준서·감사기준", str(len(refs)), "종", "검토 영역에 연결")],
    [(p["name"], len(p["risks"])) for p in sorted(profiles, key=lambda p: -len(p["risks"]))[:8]], "검토 영역이 많은 산업 (상위 8)",
)

with st.container(horizontal=True, horizontal_alignment="center", gap="small"):
    if st.button("기업 분석으로", icon=":material/domain:", type="primary", key="to_company"):
        st.switch_page("app_pages/company.py")

# 산업 카드
ui.section("산업 카드", "카드마다 한 줄 요약, 가치사슬, 먼저 볼 검토 영역 · '초안'은 감사인 검토 전")
groups = list(dict.fromkeys(kb.industries()[p["key"]].get("group", "기타") for p in profiles))
pick = st.pills("산업군", groups, selection_mode="multi", key="ov_groups",
                format_func=lambda g: f"{g} {sum(kb.industries()[p['key']].get('group') == g for p in profiles)}")
shown = [p for p in profiles if not pick or kb.industries()[p["key"]].get("group") in pick]
with st.grid(3, gap="small", min_column_width=300):
    for p in shown:
        with st.container(border=True, height="stretch"):
            ui.industry_head(p)
            for r in p["top_risks"]:
                st.markdown(f"{PRIORITY_ICON[1]} {r['title']}")
            if st.button("깊이 보기", key=f"go_{p['key']}", icon=":material/arrow_forward:",
                         icon_position="right", width="stretch"):
                st.session_state.industry = p["key"]
                st.switch_page("app_pages/industry.py")

# 공통
ui.section("모든 산업 공통", "산업과 관계없이 감사기준이 요구하거나, 조건이 맞으면 추가되는 검토 영역")
c1, c2 = st.columns(2)
with c1.container(border=True, height="stretch"):
    st.markdown("**감사기준상 상시 고려**")
    for r in kb.baseline_risks():
        st.markdown(f"{PRIORITY_ICON[r['priority']]} **{r['title']}** :gray-badge[{', '.join(r['references'])}]")
        st.caption(r["trait"])
with c2.container(border=True, height="stretch"):
    st.markdown("**조건에 따라 추가**")
    for name, when in (("going_concern", "재무 지표에서 계속기업 관련 주의·위험 신호가 보일 때"),
                       ("first_year", "초도감사일 때")):
        r = kb.conditional_risk(name)["risk"]
        st.markdown(f"{PRIORITY_ICON[r['priority']]} **{r['title']}** :gray-badge[{', '.join(r['references'])}]")
        st.caption(when)

# 작동 원리
ui.section("작동 원리", "무엇을 코드가 하고, 무엇을 지식베이스가 하는지")
ui.flow()
