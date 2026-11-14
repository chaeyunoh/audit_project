"""계획 중요성 설정 패널 (감사기준서 320).

탭보다 위에서 그린다. 감사인이 기준을 바꾸면 그 결과가 같은 실행 안에서 Risk Map·재무 신호·
특수관계자 교차점검·브리핑에 모두 반영되어야 하기 때문이다.
"""
from __future__ import annotations

import streamlit as st

from scanner import materiality as mt
from scanner.models import Report


def fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "N/A"
    if unit == "억원" and abs(v) >= 10000:
        return f"{v / 10000:,.2f}조원"
    return f"{v:,.1f}{unit}"


def badge(level: str | None) -> str:
    return f":{mt.LEVEL_BADGE[level]}-badge[{level}]" if level else ""


def panel(r: Report) -> mt.Materiality | None:
    """설정 위젯을 그리고, 감사인이 고른 값으로 계산한 중요성을 report에 반영해 돌려준다."""
    fd, sug = r.financials, r.materiality_suggested
    if not fd or not sug:
        return None
    benches = mt.benchmarks()
    cfg = mt.config()
    with st.expander(f"계획 중요성 (감사기준서 320) · {sug.benchmark_name} 기준 제안", icon=":material/scale:"):
        st.caption(f"도구 제안: {sug.suggestion}. 기준·비율은 소속 법인 방법론에 따라 감사인이 정합니다.")
        c1, c2, c3, c4 = st.columns(4, vertical_alignment="bottom")
        key = c1.selectbox("기준", list(benches), index=list(benches).index(sug.benchmark),
                           format_func=lambda k: benches[k]["name"], key="mat_bench",
                           help="\n".join(f"- {b['name']}: {b['range']} — {b['note']}" for b in benches.values()))
        # 기준을 바꾸면 그 기준의 예시 비율에서 다시 시작하도록 기준별 키를 쓴다
        pct = c2.number_input("비율(%)", 0.1, 20.0, float(benches[key]["pct"]), 0.1, key=f"mat_pct_{key}",
                              help=f"실무 범위 예시 {benches[key]['range']}")
        perf = c3.number_input("수행 중요성(%)", 10.0, 100.0, float(sug.perf_pct), 5.0, key="mat_perf",
                               help=f"위험이 높으면 낮춘다 (예시: 보통 {cfg['performance_pct']['normal']}%, "
                                    f"높음 {cfg['performance_pct']['higher_risk']}%)")
        triv = c4.number_input("명백히 사소한 금액(%)", 1.0, 20.0, float(sug.trivial_pct), 1.0, key="mat_triv")
        m = mt.compute(fd, key, pct, perf, triv, suggestion=sug.suggestion)
        changed = (key, pct, perf, triv) != (sug.benchmark, sug.pct, sug.perf_pct, sug.trivial_pct)
        if not m.ok:
            st.warning(m.note, title="계산 불가")
        else:
            with st.grid(4, gap="small", min_column_width=150):
                st.metric(f"{m.benchmark_name} ({m.year})", fmt(m.base, m.unit), border=True)
                st.metric("계획 중요성", fmt(m.overall, m.unit), border=True, help=f"{m.benchmark_name} × {m.pct:g}%")
                st.metric("수행 중요성", fmt(m.performance, m.unit), border=True, help=f"계획 중요성 × {m.perf_pct:g}%")
                st.metric("명백히 사소한 금액", fmt(m.trivial, m.unit), border=True,
                          help=f"계획 중요성 × {m.trivial_pct:g}%")
            if changed:
                st.caption(":material/edit: 감사인이 제안값을 변경함 — 브리핑에 변경 사실과 제안 근거가 함께 기록됩니다.")
    r.materiality = m if m.ok else sug
    return r.materiality if r.materiality.ok else None
