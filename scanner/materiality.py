"""계획 중요성 (감사기준서 320).

재무 신호는 '비율이 얼마나 움직였나'만 본다. 이 모듈은 그 움직임이 **금액으로 중요한가**를 붙인다.

  - 기준(세전이익·매출·총자산·자본)과 비율은 지식베이스의 예시값에서 시작하고, 감사인이 바꾼다.
  - 도구는 기준을 '제안'만 한다 (세전이익이 손실이거나 변동이 크면 매출 기준을 제안).
  - 비교는 방향과 무관하게 절대값으로 하고, 기준 '이상'이면 해당 수준으로 본다.
  - 결과는 '확인할 곳의 크기'에 대한 표시일 뿐, 왜곡표시 여부에 대한 판단이 아니다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from . import kb
from .finance import ACCOUNT_LABEL, FinancialData

Level = Literal["계획 중요성 이상", "수행 중요성 이상", "명백히 사소한 금액 초과", "명백히 사소함"]
LEVEL_BADGE = {"계획 중요성 이상": "red", "수행 중요성 이상": "orange",
               "명백히 사소한 금액 초과": "blue", "명백히 사소함": "gray"}
_UNIT_WON = {"원": 1, "천원": 1e3, "백만원": 1e6, "억원": 1e8}


class Materiality(BaseModel):
    benchmark: str
    benchmark_name: str
    year: int
    base: float | None
    pct: float
    perf_pct: float
    trivial_pct: float
    overall: float | None = None
    performance: float | None = None
    trivial: float | None = None
    unit: str = "억원"
    ok: bool = False
    note: str = ""
    suggestion: str = ""          # 도구가 제안한 이유 (감사인이 바꾸면 그대로 남겨 비교 가능)


def config() -> dict:
    return kb.load_kb()["materiality"]


def benchmarks() -> dict[str, dict]:
    return {b["key"]: b for b in config()["benchmarks"]}


def suggest(fd: FinancialData, with_perf: bool = False, higher_risk: bool = False):
    """(기준 키, 이유) — with_perf면 (기준 키, 이유, 수행 중요성 비율)."""
    cfg = config()
    y, py = fd.years[-1], fd.years[-2]
    pti, prev = fd.get("pretax_income", y), fd.get("pretax_income", py)
    if pti is None:
        key, why = "revenue", "세전이익을 공시에서 찾지 못해 매출 기준을 제안"
    elif pti <= 0:
        key, why = "revenue", f"{y}년 세전이익이 0 이하({pti:,.0f}{fd.unit})여서 매출 기준을 제안"
    elif prev not in (None, 0) and abs(pti - prev) / abs(prev) * 100 >= cfg["volatility_limit"]:
        chg = (pti - prev) / abs(prev) * 100
        key, why = "revenue", f"세전이익이 전년 대비 {chg:+.0f}% 변동해 기준으로 불안정 — 매출 기준을 제안"
    else:
        key, why = "pretax_income", "세전이익이 양수이고 변동이 크지 않아 세전이익 기준을 제안"
    if not with_perf:
        return key, why
    perf = cfg["performance_pct"]["higher_risk" if higher_risk else "normal"]
    why += (f" · 위험 요인(초도감사·계속기업 신호)이 있어 수행 중요성 {perf}% 제안" if higher_risk
            else f" · 수행 중요성 {perf}% 제안")
    return key, why, perf


def compute(fd: FinancialData, benchmark: str, pct: float, perf_pct: float, trivial_pct: float,
            suggestion: str = "") -> Materiality:
    y = fd.years[-1]
    name = benchmarks().get(benchmark, {}).get("name") or ACCOUNT_LABEL.get(benchmark, benchmark)
    base = fd.get(benchmark, y)
    m = Materiality(benchmark=benchmark, benchmark_name=name, year=y, base=base, pct=pct, perf_pct=perf_pct,
                    trivial_pct=trivial_pct, unit=fd.unit, suggestion=suggestion)
    if base is None:
        m.note = f"{y}년 {name}을(를) 공시에서 찾지 못함 — 다른 기준을 고르세요"
        return m
    if base <= 0:
        m.note = f"{y}년 {name}이(가) 0 이하({base:,.0f}{fd.unit}) — 기준으로 쓸 수 없음"
        return m
    m.overall = round(base * pct / 100, 1)
    m.performance = round(m.overall * perf_pct / 100, 1)
    m.trivial = round(m.overall * trivial_pct / 100, 1)
    m.ok = True
    return m


def default(fd: FinancialData, higher_risk: bool) -> Materiality:
    key, why, perf = suggest(fd, with_perf=True, higher_risk=higher_risk)
    return compute(fd, key, benchmarks()[key]["pct"], perf, config()["trivial_pct"], suggestion=why)


def classify(amount: float | None, m: Materiality) -> Level | None:
    if amount is None or not m.ok:
        return None
    a = abs(amount)
    if a >= m.overall:
        return "계획 중요성 이상"
    if a >= m.performance:
        return "수행 중요성 이상"
    if a >= m.trivial:
        return "명백히 사소한 금액 초과"
    return "명백히 사소함"


def won_to_unit(won: float | None, unit: str) -> float | None:
    return None if won is None else won / _UNIT_WON.get(unit, 1)


def signal_levels(report, m: Materiality) -> dict[int, Level | None]:
    """id(FinancialSignal) → 수준. 계정 금액 변동(분자 계정)으로 비교한다."""
    sigs = list(report.overview_signals) + [s for k in report.risks for s in k.fin_signals]
    return {id(s): classify(s.amount_change, m) for s in sigs}


def discrepancy_levels(report, m: Materiality) -> dict[int, Level | None]:
    """id(Discrepancy) → 수준. 금액 차이가 있는 불일치만 값이 있다."""
    if not report.rpt:
        return {}
    return {id(d): classify(won_to_unit(d.gap_won, m.unit), m) for d in report.rpt.discrepancies}
