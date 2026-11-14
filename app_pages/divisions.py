"""본부별 산업 지도 — 회계법인 본부(조직) 체계로 산업을 묶어 본다.

본부를 고르면 그 본부가 맡는 섹터와, 지식베이스로 바로 공부할 수 있는 섹터가 보인다.
'준비 중' 섹터는 지식베이스 확장 대상이다. 분류 근거: knowledge/sector_map.yaml
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import ui
from scanner import catalog, kb
from scanner.brief import PRIORITY_ICON

systems = catalog.systems()
names = {s["key"]: s["name"] for s in systems}
cur = st.session_state.get("div_system", systems[0]["key"])
sel = st.segmented_control("본부 체계", list(names), default=cur, format_func=names.get)
st.session_state.div_system = sel or cur
sys_ = catalog.system(st.session_state.div_system)

divs = sys_["divisions"]
ind_divs = [d for d in divs if d.get("kind") != "function"]
cov = [catalog.coverage(d) for d in ind_divs]
ready, total = sum(c for c, _ in cov), sum(t for _, t in cov)
with st.grid(4, gap="small", min_column_width=150):
    st.metric("산업 본부", len(ind_divs), border=True)
    st.metric("기능 본부", len(divs) - len(ind_divs), border=True, help="감사·인증 등 산업과 무관하게 일하는 본부")
    st.metric("섹터", total, border=True)
    st.metric("지식베이스로 준비된 섹터", f"{ready} / {total}", border=True,
              help="'준비 중' 섹터는 산업 지식베이스를 추가하면 바로 깊이 보기·비교에 들어옵니다.")

ui.section("본부 카드", "섹터 버튼을 누르면 그 산업의 깊이 보기로 이동합니다")
with st.grid(3, gap="small", min_column_width=280):
    for d in divs:
        with st.container(border=True, height="stretch"):
            c, t = catalog.coverage(d)
            ui.division_head(d, c, t)
            if d.get("kind") == "function":
                st.markdown("**주로 보는 산업 공통 영역**")
                for r in catalog.focus_risks(d):
                    st.markdown(f"{PRIORITY_ICON[r['priority']]} {r['title']} :gray-badge[{', '.join(r['references'])}]")
                continue
            with st.container(horizontal=True, gap="small"):
                for sec in d["sectors"]:
                    if sec.get("kb"):
                        if st.button(sec["name"], key=f"sec_{sys_['key']}_{d['code']}_{sec['name']}",
                                     icon=":material/arrow_forward:", icon_position="right"):
                            st.session_state.industry = sec["kb"]
                            st.switch_page("app_pages/industry.py")
                    else:
                        ui.block(ui.chip(f"{sec['name']} · 준비 중", "todo"))

todo = list(dict.fromkeys(sec["name"] for d in ind_divs for sec in d["sectors"] if not sec.get("kb")))
if todo:
    ui.section("지식베이스 확장 후보", f"이 체계에서 아직 준비되지 않은 섹터 {len(todo)}개")
    ui.block('<div style="display:flex;flex-wrap:wrap;gap:6px">' + "".join(ui.chip(x, "todo") for x in todo) + "</div>")

ui.section("산업 ↔ 본부 대응표", "지식베이스의 각 산업을 두 체계에서 어느 본부가 맡는지")
rows = []
for k, ind in kb.industries().items():
    row = {"산업": ind["name"]}
    for s in systems:
        row[s["name"]] = ", ".join(f"{x['본부']} ({x['섹터']})" for x in catalog.divisions_of(k) if x["체계"] == s["name"]) or "—"
    rows.append(row)
st.dataframe(pd.DataFrame(rows), hide_index=True, alt="지식베이스 산업별로 두 본부 체계에서 맡는 본부")
st.caption(f"분류 기준: knowledge/sector_map.yaml v{catalog.sector_map()['map_version']} · "
           "본부-산업 연결에는 작성자 판단이 섞여 있으니 실제 조직 기준으로 확인하세요.")
