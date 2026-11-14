"""⑤ Financial Signals 탭 화면.

시각화 원칙
  - 좋음/나쁨을 빨강·초록으로 칠하지 않는다. 기본은 중립색, 기준을 넘은 지점만 주황으로 강조한다.
  - 막대는 0에서 시작, 3개년 추이만 단순하게 그린다.
  - 문구는 '이상 있음'이 아니라 '변동 + 확인 필요'로 쓴다.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import mat_view
from scanner import materiality as mt
from scanner.finance import FinancialSignal, chart_frame, metric_frame
from scanner.models import Report

NEUTRAL, ACCENT = "#8a8f98", "#e8710a"


def _pct(a: float | None, b: float | None) -> float | None:
    return None if a is None or b in (None, 0) else round((a - b) / abs(b) * 100, 1)


def _money(v: float, unit: str) -> str:
    """억원 단위가 1만을 넘으면 조원으로 줄여 카드에서 잘리지 않게 한다."""
    if unit == "억원" and abs(v) >= 10000:
        return f"{v / 10000:,.1f}조원"
    return f"{v:,.0f}{unit}"


def kpi_row(r: Report):
    fd = r.financials
    y, py = fd.years[-1], fd.years[-2]
    ov = {s.metric: s for s in r.overview_signals}

    def amount(label: str, key: str):
        vals = [fd.get(key, yy) for yy in fd.years]
        cur = fd.get(key, y)
        if cur is None:
            st.metric(label, "N/A", border=True, height="stretch", help="공시에서 계정을 찾지 못함")
            return
        chg = _pct(cur, fd.get(key, py))
        st.metric(label, _money(cur, fd.unit), None if chg is None else f"{chg:+.1f}%",
                  delta_color="off", delta_description=f"vs {py}", border=True, height="stretch",
                  chart_data=[v for v in vals if v is not None], chart_type="bar")

    def ratio(label: str, s: FinancialSignal | None):
        if not s or s.values.get(y) is None:
            st.metric(label, "N/A", border=True, height="stretch")
            return
        st.metric(label, f"{s.values[y]:,.1f}%", None if s.change is None else f"{s.change:+.1f}%p",
                  delta_color="orange" if s.triggered else "off", delta_description=f"vs {py}",
                  border=True, height="stretch",
                  chart_data=[v for v in s.values.values() if v is not None], chart_type="line")

    with st.grid(5, gap="small", min_column_width=150):
        amount("매출", "revenue")
        ratio("영업이익률", ov.get("영업이익률"))
        amount("당기순이익", "net_income")
        amount("영업활동현금흐름", "cfo")
        ratio("부채비율", ov.get("부채비율"))


def earnings_vs_cash(r: Report):
    df = pd.DataFrame(chart_frame(r.financials, ["net_income", "cfo"]))
    if df.empty:
        st.caption("당기순이익·영업현금흐름 계정을 찾지 못했습니다.")
        return
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("연도:N", title=None, axis=alt.Axis(labelAngle=0)),
        xOffset="계정:N",
        y=alt.Y("금액:Q", title=f"금액({r.financials.unit})"),
        color=alt.Color("계정:N", scale=alt.Scale(range=[NEUTRAL, "#4c6ef5"]), legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["연도:N", "계정:N", alt.Tooltip("금액:Q", format=",.0f")],
    )
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#999").encode(y="y:Q")
    st.altair_chart(bars + zero, alt="연도별 당기순이익과 영업활동현금흐름 비교")


def metric_chart(s: FinancialSignal):
    df = pd.DataFrame(metric_frame(s))
    if df.empty:
        st.caption(s.note or "계산 불가")
        return
    base = alt.Chart(df).encode(x=alt.X("연도:N", title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("값:Q", title=s.unit,
                                                                    scale=alt.Scale(zero=s.unit == "일")))
    color = alt.Color("구분:N", scale=alt.Scale(domain=["추이", "확인 신호"], range=[NEUTRAL, ACCENT]), legend=None)
    chart = (base.mark_line(color=NEUTRAL)
             + base.mark_circle(size=90).encode(color=color, tooltip=["연도:N", alt.Tooltip("값:Q", format=",.1f")])
             + base.mark_text(dy=-12).encode(text=alt.Text("값:Q", format=",.1f"), color=color))
    st.altair_chart(chart.properties(height=180), alt=f"{s.metric} 3개년 추이")


def signal_status(s: FinancialSignal) -> str:
    if s.note:
        return f":gray-badge[계산 불가] {s.note}"
    if s.threshold is None:
        return ":gray-badge[참고 지표]"
    u = "%p" if s.unit in ("%", "%p") else s.unit
    sign = {"up": "+", "down": "−", "both": "±"}[s.direction]
    what = f"최근 연도 격차 {s.change:+,.1f}{u}" if s.unit == "%p" else f"전년 대비 {s.change:+,.1f}{u}"
    badge = ":orange-badge[확인 신호]" if s.triggered else ":gray-badge[기준 이내]"
    return f"{badge} {what} (기준 {sign}{s.threshold:g}{u})"


LEVEL_BADGE = {"정상": "gray", "주의": "orange", "위험": "red", "확인 필요": "blue"}


def going_concern_panel(r: Report):
    """수준 판정 4항목. 정보가 없으면 '정상'이 아니라 '확인 필요'."""
    if not r.going_concern:
        return
    with st.container(border=True):
        st.subheader("계속기업 지표판", divider="gray",
                     help="감사기준서 570의 재무적 사건·상황 예시에 대응. 주의·위험이 있으면 Risk Map에 계속기업 검토 영역이 추가됩니다.")
        with st.grid(4, gap="small", min_column_width=150):
            for c in r.going_concern:
                with st.container(border=True, height="stretch"):
                    st.markdown(f"**{c.item}**  \n:{LEVEL_BADGE[c.level]}-badge[{c.level}] {c.value}")
                    st.caption(c.reason)


def render(r: Report):
    fd = r.financials
    if not fd:
        st.info("재무 데이터가 없습니다. OpenDART 모드에서는 사업보고서 재무제표를 자동으로 수집합니다.")
        return
    st.caption(f"출처 `{fd.source_id}` {fd.publisher} · {fd.title} · {fd.basis} · 단위 {fd.unit}. "
               "모든 숫자는 공시 원본에서 코드로 계산했으며 AI를 거치지 않습니다.")
    # 이 회사의 지표 계산에 실제로 필요한 계정만 경고한다 (건설업이 아닌 회사에 '계약자산 없음'은 소음)
    needed = {acc for s in r.overview_signals + [x for k in r.risks for x in k.fin_signals] for acc in s.accounts}
    missing = [a for a in fd.unmapped if a in needed]
    if missing:
        st.caption(f"⚠️ 지표 계산에 필요한데 공시에서 찾지 못한 계정: {', '.join(missing)}")

    kpi_row(r)
    going_concern_panel(r)

    with st.container(border=True):
        st.subheader("이익과 현금흐름", divider="gray")
        earnings_vs_cash(r)
        cash = next((s for s in r.overview_signals if s.metric.startswith("영업현금흐름")), None)
        if cash:
            st.markdown(signal_status(cash))
            if cash.question:
                st.markdown(f":orange-badge[확인 질문] {cash.question}")

    st.subheader("위험 영역별 재무 지표")
    st.caption("지식베이스가 위험 영역마다 정한 지표와 기준입니다. 기준을 넘은 값은 결론이 아니라 '확인할 곳'을 뜻합니다.")
    titles = {k.risk_id: k.title for k in r.risks}
    signals = [s for k in r.risks for s in k.fin_signals]
    levels = mt.signal_levels(r, r.materiality) if r.materiality and r.materiality.ok else {}
    order = list(mt.LEVEL_BADGE)
    # 확인 신호 먼저, 그 안에서는 금액이 중요한 순
    signals.sort(key=lambda s: (not s.triggered, order.index(levels[id(s)]) if levels.get(id(s)) else 9))
    if levels:
        st.caption("금액은 '기대치 대비 차이'입니다: 전년 비율이 유지됐다면 있었을 금액(기대치)과 실제 금액의 차이 "
                   f"(감사기준서 520). 계획 중요성 {mat_view.fmt(r.materiality.overall, fd.unit)} · "
                   f"수행 중요성 {mat_view.fmt(r.materiality.performance, fd.unit)} 기준.")
    cols = st.columns(2)
    for i, s in enumerate(signals):
        with cols[i % 2].container(border=True):
            st.markdown(f"**{s.metric}**  \n{titles.get(s.risk_id, '')}")
            st.caption(s.formula)
            metric_chart(s)
            st.markdown(signal_status(s))
            if s.amount_change is not None:
                st.markdown(f"{s.amount_account} 기대치 대비 {s.amount_change:+,.0f}{fd.unit} "
                            f"{mat_view.badge(levels.get(id(s)))}")
                st.caption(f"기대치 {s.expected:,.0f}{fd.unit} (전년 비율 유지 가정)")

    rows = [{"위험 영역": titles.get(s.risk_id, "개요"), "지표": s.metric, "단위": s.unit,
             **{str(y): s.values.get(y) for y in fd.years}, "전년 대비": s.change, "기준": s.threshold,
             "상태": "확인 신호" if s.triggered else ("계산 불가" if s.note else "-"),
             f"기대치({fd.unit})": s.expected, f"기대치 대비 차이({fd.unit})": s.amount_change,
             "중요성 대비": levels.get(id(s)) or "-"}
            for s in r.overview_signals + signals]
    with st.expander("전체 지표 표"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, alt="위험 영역별 재무 지표 3개년 값과 확인 신호")
