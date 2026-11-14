"""산업 비교 — 여러 산업을 나란히 놓고 감사 초점의 차이와 공통점을 본다."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import industry_view as iv
from scanner import catalog, kb
from scanner.brief import PRIORITY_ICON

keys_all = list(kb.industries())
keys = st.pills("비교할 산업", keys_all, selection_mode="multi", default=keys_all,
                format_func=lambda k: kb.industries()[k]["name"]) or keys_all
profiles = [catalog.profile(k) for k in keys]

# 1. 나란히
st.subheader("1. 한 줄 요약과 먼저 볼 곳")
with st.grid(min(len(profiles), 4), gap="small", min_column_width=240):
    for p in profiles:
        with st.container(border=True, height="stretch"):
            st.markdown(f"**{p['name']}**")
            st.caption(p["summary"])
            st.markdown(" → ".join(p["value_chain"]))
            for r in p["top_risks"]:
                st.markdown(f"{PRIORITY_ICON[1]} {r['title']}")

# 2. 주장 히트맵
st.subheader("2. 산업마다 무게가 실리는 경영진 주장")
st.caption("숫자는 그 주장이 걸린 검토 영역 수입니다. 진할수록 그 산업 감사에서 자주 확인하게 되는 주장입니다.")
iv.assertion_heatmap(keys)
for p in profiles:
    top = [a for a, _ in p["assertions"].most_common(2)]
    st.markdown(f"- **{p['name']}**: {' · '.join(top)} 중심")
iv.assertion_glossary()

# 3. 공통 기준
st.subheader("3. 여러 산업에 걸쳐 쓰이는 기준")
st.caption("같은 기준서가 산업마다 다른 모습으로 나타납니다. 한 산업에서 익힌 기준을 다른 산업으로 넓히는 출발점입니다.")
refs = pd.DataFrame(catalog.shared_references(keys))
st.dataframe(refs, hide_index=True, alt="기준서별로 쓰이는 산업과 검토 영역")

# 4. 공통 재무 지표
st.subheader("4. 같은 지표, 다른 의미")
rows = [{"지표": m["지표"], "산업": p["name"], "이 산업에서 보는 이유": m["검토 영역"]}
        for p in profiles for m in p["metrics"]]
if rows:
    df = pd.DataFrame(rows)
    pivot = df.pivot_table(index="지표", columns="산업", values="이 산업에서 보는 이유",
                           aggfunc=lambda s: ", ".join(s)).fillna("—").reset_index()
    pivot.insert(1, "산업 수", (pivot.drop(columns="지표") != "—").sum(axis=1))
    st.dataframe(pivot.sort_values("산업 수", ascending=False), hide_index=True,
                 alt="재무 지표별로 산업마다 연결된 검토 영역")
