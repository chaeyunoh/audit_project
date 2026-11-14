"""최근 주요 공시 — OpenDART 공시 목록(공개정보)을 기업 분석 화면에 보여준다.

  - 회사 머리 아래: 주요 공시 카드 4개 (반복 신고·정기보고는 뒤로)
  - '공시 뉴스' 탭: 타임라인 · 주제별 건수 · 주제별 감사 포인트 · 원문 링크가 있는 전체 목록
분류는 제목 키워드뿐이며 공시 내용을 판단하지 않는다. 화면을 열 때 DART에서 새로 받아 1시간 캐시한다.
"""
from __future__ import annotations

import os

import altair as alt
import pandas as pd
import streamlit as st

from scanner import collect
from scanner import disclosures as ds
from scanner.models import Report

TOPIC_COLOR = {"소송·제재·사고": "#C0261A", "자금조달·자본": "#B45309", "합병·분할·투자": "#5B4BC4",
               "계약·수주": "#2F7FE0", "지배구조·주주": "#1F7A4D", "실적·배당": "#0B0B0C",
               "정기·감사보고": "#A9CFF5", "기타": "#9A9AA0"}
TOPIC_BADGE = {"소송·제재·사고": "red", "자금조달·자본": "orange", "합병·분할·투자": "violet", "계약·수주": "blue",
               "지배구조·주주": "green", "실적·배당": "gray", "정기·감사보고": "blue", "기타": "gray"}
DAYS = 365


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _fetch(corp_code: str, stock_code: str, days: int) -> tuple[list[dict], str]:
    """(공시 행, 안내 메시지). 키는 캐시 인자에 넣지 않는다."""
    key = os.getenv("DART_API_KEY", "")
    if not key:
        return [], "DART_API_KEY가 없어 최근 공시를 불러올 수 없습니다."
    try:
        c = collect.DartCollector(key, timeout=15)
        code = corp_code or c.corp_code_for_stock(stock_code)
        if not code:
            return [], "DART 고유번호를 찾지 못해 최근 공시를 불러올 수 없습니다."
        return ds.normalize(c.recent_disclosures(code, days=days)), ""
    except collect.CollectError as e:
        return [], str(e)


def load(r: Report) -> tuple[list[dict], str]:
    p = r.company_profile or {}
    stock = r.stock_code or p.get("stock_code", "")
    if not p or not (p.get("corp_code") or stock):
        return [], "데모·업로드 자료는 DART 공시 목록이 없습니다."
    return _fetch(p.get("corp_code", ""), stock, DAYS)


def _flags(x: dict) -> str:
    return " ".join(b for b, on in ((":orange-badge[정정 공시]", x["correction"]),
                                    (":gray-badge[이후 정정 있음]", x["later_corrected"])) if on)


# ---------------------------------------------------------------- 회사 머리 아래 카드
def strip(r: Report, rows: list[dict], msg: str):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**최근 주요 공시** :small[최근 {DAYS}일 · OpenDART · 반복 신고 제외]")
        st.space("stretch")
        if rows:
            st.caption(f"최신 {len(rows)}건 전체는 '공시 뉴스' 탭")
    if not rows:
        st.caption(msg or "최근 1년간 공시가 없습니다.")
        return
    with st.grid(4, gap="small", min_column_width=220):
        for x in ds.highlights(rows, 4):
            with st.container(border=True, height="stretch"):
                st.markdown(f":{TOPIC_BADGE[x['topic']]}-badge[{x['topic']}] :small[{x['date']}]")
                st.markdown(f"**{x['title']}**")
                if _flags(x):
                    st.markdown(_flags(x))
                st.markdown(f":small[{ds.TOPIC_NOTE[x['topic']]}]  \n[DART 원문 ↗]({x['url']})")


# ---------------------------------------------------------------- 탭
def timeline(df: pd.DataFrame, company: str):
    present = [t for t in ds.TOPIC_ORDER if t in set(df["주제"])]
    chart = alt.Chart(df).mark_circle(size=110, opacity=.85, stroke="white", strokeWidth=1).encode(
        x=alt.X("접수일:T", title=None, axis=alt.Axis(format="%y.%m", labelAngle=0, tickCount="month")),
        y=alt.Y("주제:N", sort=present, title=None),
        color=alt.Color("주제:N", sort=present, legend=None,
                        scale=alt.Scale(domain=present, range=[TOPIC_COLOR[t] for t in present])),
        tooltip=[alt.Tooltip("접수일:T", format="%Y-%m-%d"), "주제:N", "공시명:N", "제출인:N"])
    st.altair_chart(chart.properties(height=40 * len(present) + 40), alt=f"{company} 최근 공시를 주제별로 날짜에 찍은 타임라인")


def topic_bars(df: pd.DataFrame):
    cnt = df.groupby("주제").size().reset_index(name="건수")
    cnt["감사에서 볼 점"] = cnt["주제"].map(ds.TOPIC_NOTE)
    present = [t for t in ds.TOPIC_ORDER if t in set(cnt["주제"])]
    base = alt.Chart(cnt).encode(y=alt.Y("주제:N", sort=present, title=None))
    bar = base.mark_bar(cornerRadiusEnd=4, height=16).encode(
        x=alt.X("건수:Q", title="공시 수", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("주제:N", legend=None, scale=alt.Scale(domain=present, range=[TOPIC_COLOR[t] for t in present])),
        tooltip=["주제:N", "건수:Q", "감사에서 볼 점:N"])
    txt = base.mark_text(align="left", dx=4, fontWeight=600).encode(x="건수:Q", text="건수:Q")
    st.altair_chart((bar + txt).properties(height=40 * len(present) + 40), alt="주제별 공시 건수")


def render(r: Report, rows: list[dict], msg: str):
    if not rows:
        st.info(msg or "최근 1년간 공시가 없습니다.")
        return
    st.caption(f"OpenDART 공시 목록 최근 {DAYS}일 · 최신 {len(rows)}건. 주제는 공시 제목 키워드로만 붙였습니다 "
               "(내용 판단 아님). 정정 공시는 원 공시와 함께 보세요.")
    df = pd.DataFrame([{"접수일": x["date"], "주제": x["topic"], "공시명": x["title"], "제출인": x["filer"],
                        "정정": "정정" if x["correction"] else ("이후 정정" if x["later_corrected"] else ""),
                        "반복 신고": ds.is_repetitive(x["title"]), "원문": x["url"]} for x in rows])
    df["접수일"] = pd.to_datetime(df["접수일"], errors="coerce")

    c1, c2 = st.columns([1.7, 1], gap="medium")
    with c1.container(border=True, height="stretch"):
        st.markdown("**공시 타임라인** — 점 하나가 공시 한 건")
        timeline(df, r.company)
    with c2.container(border=True, height="stretch"):
        st.markdown("**주제별 건수**")
        topic_bars(df)

    present = [t for t in ds.TOPIC_ORDER if t in set(df["주제"]) and ds.TOPIC_NOTE[t]]
    if present:
        st.markdown("**주제별로 감사에서 볼 점**")
        with st.grid(3, gap="small", min_column_width=240):
            for t in present:
                sub = df[df["주제"] == t]
                with st.container(border=True, height="stretch"):
                    st.markdown(f":{TOPIC_BADGE[t]}-badge[{t}] **{len(sub)}건**")
                    st.caption(ds.TOPIC_NOTE[t])
                    st.markdown(f":small[최근: {sub.iloc[0]['공시명']}]")

    st.markdown("**전체 공시 목록**")
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        pick = st.pills("주제", [t for t in ds.TOPIC_ORDER if t in set(df["주제"])], selection_mode="multi",
                        key="disc_topics", label_visibility="collapsed")
        hide = st.toggle("반복 신고 숨기기", value=True, key="disc_hide",
                         help="임원·주요주주 지분 변동, IR 안내 등 자주 반복되는 신고")
    view = df[df["주제"].isin(pick)] if pick else df
    if hide:
        view = view[~view["반복 신고"]]
    st.dataframe(view.drop(columns=["반복 신고"]), hide_index=True, width="stretch",
                 column_config={"접수일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                                "공시명": st.column_config.TextColumn(width="large"),
                                "원문": st.column_config.LinkColumn(display_text="DART ↗")},
                 alt=f"{r.company} 최근 공시 목록")
