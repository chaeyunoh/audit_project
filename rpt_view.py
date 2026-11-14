"""⑥ 특수관계자 교차점검 탭 화면 (감사기준서 550)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import mat_view
from scanner import materiality as mt
from scanner.models import Report
from scanner.related_party import STATUS_LABEL, Extraction

STATUS_BADGE = {"ok": "gray", "partial": "orange", "failed": "red", "not_run": "blue", "no_source": "blue"}


def _extraction(ex: Extraction):
    with st.container(border=True):
        st.markdown(f"**{ex.label}** `{ex.source_id or '-'}`")
        origin = {"AI": ":violet-badge[AI 추출]", "데모 고정 응답": ":gray-badge[데모 고정 응답 · AI 아님]"}.get(ex.origin, "")
        st.markdown(f":{STATUS_BADGE[ex.status]}-badge[{STATUS_LABEL[ex.status]}] {origin}"
                    + (" :orange-badge[원문 일부만 읽음]" if ex.truncated else ""))
        if ex.truncated:
            st.caption("원문이 길어 앞부분만 비교했습니다. 이 쪽에 '없다'는 결론은 내지 않고, 원문 확인 질문으로 넘깁니다.")
        if ex.items:
            st.dataframe(pd.DataFrame([{"거래상대방": i.related_party, "관계": i.relationship,
                                        "거래 유형": i.transaction_type, "금액": i.amount, "원문 인용": i.quote}
                                       for i in ex.items]),
                         hide_index=True, alt=f"{ex.label}에서 원문 대조를 통과한 특수관계자 거래")
        elif ex.status in ("ok",):
            st.caption("원문 대조를 통과한 거래가 없습니다 (거래 없음 응답).")
        if ex.dropped:
            with st.expander(f"원문 대조에서 제외된 항목 {len(ex.dropped)}건"):
                for d in ex.dropped:
                    st.markdown(f"- :red-badge[{d['reason']}] “{d['detail']}”")


def render(r: Report):
    rpt = r.rpt
    st.caption("AI(또는 데모 고정 응답)는 표를 옮겨 적기만 합니다. 인용문이 원문에 글자 그대로 없거나 값이 인용문 밖에 있으면 "
               "제외하고, 비교·금액 단위 환산·불일치 판정은 코드가 합니다.")
    if not rpt:
        st.info("특수관계자 거래 원문 구간이 없습니다.")
        return
    c1, c2 = st.columns(2)
    with c1:
        _extraction(rpt.business)
    with c2:
        _extraction(rpt.notes)

    st.subheader("두 기재의 불일치")
    usable = {"ok", "partial"}
    if rpt.business.status not in usable or rpt.notes.status not in usable:
        st.warning("한쪽 이상의 추출 결과가 없어 비교하지 않았습니다. 불일치가 없다는 뜻이 아닙니다.", title="확인 필요")
    elif not rpt.discrepancies:
        if rpt.conclusive:
            st.success("원문 대조를 통과한 항목 사이에서는 불일치가 발견되지 않았습니다.")
        else:
            st.info("비교한 항목 사이에서는 불일치가 없지만, 제외된 항목이 있어 원문 확인이 필요합니다.")
    m = r.materiality if r.materiality and r.materiality.ok else None
    levels = mt.discrepancy_levels(r, m) if m else {}
    for d in rpt.discrepancies:
        with st.container(border=True):
            st.markdown(f":orange-badge[불일치] {d.issue}")
            if d.gap_won is not None and m:
                gap = mt.won_to_unit(d.gap_won, m.unit)
                st.markdown(f"차이 {mat_view.fmt(gap, m.unit)} {mat_view.badge(levels.get(id(d)))}")
            st.caption(d.evidence)
