"""재무 신호 — 위험 영역과 연결된 계정의 숫자가 실제로 어떻게 움직였는가.

감사기준서 520의 '계획단계 분석적 절차'를 Risk Map에 붙이는 모듈이다.

원칙
  - 숫자는 DART 재무제표 API 원본에서만 가져오고, 계산은 전부 이 코드가 한다.
    AI는 재무 숫자를 읽지도 계산하지도 않는다 (수치 날조 차단 원칙 유지).
  - 어떤 위험에 어떤 지표를 볼지, 기준값은 얼마인지는 지식베이스(industry_kb.yaml)에서만 정한다.
  - 기준을 넘으면 '이상'이 아니라 '확인 신호'로 표시하고, 숫자를 채운 확인 질문을 만든다.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from . import kb

# 표준 계정 키 → (DART account_id 후보, 계정명 후보). account_id 우선, 없으면 계정명.
ACCOUNT_MAP: dict[str, tuple[list[str], list[str]]] = {
    "revenue": (["ifrs-full_Revenue"], ["매출액", "수익(매출액)", "영업수익", "매출"]),
    "cogs": (["ifrs-full_CostOfSales"], ["매출원가", "영업비용"]),
    "operating_income": (["dart_OperatingIncomeLoss"], ["영업이익", "영업이익(손실)"]),
    "net_income": (["ifrs-full_ProfitLoss"], ["당기순이익", "당기순이익(손실)", "연결당기순이익"]),
    "pretax_income": (["ifrs-full_ProfitLossBeforeTax"],
                      ["법인세비용차감전순이익", "법인세비용차감전순이익(손실)", "법인세차감전순이익"]),
    "cfo": (["ifrs-full_CashFlowsFromUsedInOperatingActivities"], ["영업활동현금흐름", "영업활동으로 인한 현금흐름"]),
    "capex": (["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"], ["유형자산의 취득"]),
    "receivables": (["ifrs-full_TradeAndOtherCurrentReceivables", "dart_ShortTermTradeReceivable",
                     "ifrs-full_CurrentTradeReceivables"], ["매출채권", "매출채권 및 기타채권", "공사미수금"]),
    "contract_assets": (["ifrs-full_CurrentContractAssets", "ifrs-full_ContractAssets"], ["계약자산", "미청구공사"]),
    "inventory": (["ifrs-full_Inventories"], ["재고자산"]),
    "ppe": (["ifrs-full_PropertyPlantAndEquipment"], ["유형자산"]),
    "total_assets": (["ifrs-full_Assets"], ["자산총계"]),
    "total_liabilities": (["ifrs-full_Liabilities"], ["부채총계"]),
    "total_equity": (["ifrs-full_Equity"], ["자본총계"]),
    "capital_stock": (["ifrs-full_IssuedCapital"], ["자본금"]),
}
ACCOUNT_LABEL = {
    "revenue": "매출", "cogs": "매출원가", "operating_income": "영업이익", "net_income": "당기순이익",
    "pretax_income": "법인세비용차감전순이익",
    "cfo": "영업활동현금흐름", "capex": "유형자산 취득", "receivables": "매출채권",
    "contract_assets": "계약자산", "inventory": "재고자산", "ppe": "유형자산",
    "total_assets": "자산총계", "total_liabilities": "부채총계", "total_equity": "자본총계",
    "capital_stock": "자본금",
}


class FinancialData(BaseModel):
    source_id: str = "F01"
    title: str                                  # 예: 사업보고서(2025.12) 연결재무제표
    publisher: str = "DART"
    url: str = ""
    basis: str = "연결"                          # 연결 / 별도
    unit: str = "억원"
    years: list[int]                            # 오름차순
    amounts: dict[str, dict[int, float]]        # 표준 계정 → 연도 → 금액(unit 기준)
    unmapped_note: str = ""
    unmapped: list[str] = Field(default_factory=list)  # 매핑 못 한 계정 라벨

    def get(self, key: str, year: int) -> float | None:
        return self.amounts.get(key, {}).get(year)


class FinancialSignal(BaseModel):
    risk_id: str | None                         # None = 개요 지표
    metric: str
    unit: Literal["%", "일", "%p"]
    values: dict[int, float | None]
    accounts: list[str]                         # 계산에 쓴 계정(라벨)
    change: float | None = None                 # 최근 연도 - 전년
    threshold: float | None = None
    direction: Literal["up", "down", "both"] = "both"
    triggered: bool = False
    note: str = ""                              # 계산 불가 사유 등
    question: str = ""
    formula: str = ""
    # 분석적 절차(감사기준서 520)의 '기대치 대비 차이' — 중요성 비교용 (unit 기준)
    #   기대치 = 전년 분자 × (당기 분모 ÷ 전년 분모)  … 전년 비율·관계가 유지됐다면 있었을 금액
    #   차이   = 당기 분자 − 기대치
    amount_change: float | None = None
    expected: float | None = None
    amount_account: str = ""


# ---------------- DART 원본 → 표준 계정 ----------------
def _num(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(",", "")
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


def from_dart_rows(rows: list[dict], bsns_year: int, title: str, url: str, basis: str,
                   scale: float = 1e8, unit: str = "억원") -> FinancialData:
    """fnlttSinglAcntAll.json의 list → FinancialData. 금액은 원 → 억원으로 환산."""
    years = [bsns_year - 2, bsns_year - 1, bsns_year]
    cols = {bsns_year: "thstrm_amount", bsns_year - 1: "frmtrm_amount", bsns_year - 2: "bfefrmtrm_amount"}
    amounts: dict[str, dict[int, float]] = {}
    missing = []
    for key, (ids, names) in ACCOUNT_MAP.items():
        row = next((r for r in rows if r.get("account_id") in ids), None)
        if row is None:  # 계정명 정확 일치 → 공백 제거 일치 순
            norm = lambda x: re.sub(r"\s", "", x or "")
            row = next((r for n in names for r in rows if norm(r.get("account_nm")) == norm(n)), None)
        if row is None:
            missing.append(ACCOUNT_LABEL[key])
            continue
        vals = {y: v / scale for y, c in cols.items() if (v := _num(row.get(c))) is not None}
        if key == "capex":  # 현금흐름표상 취득은 음수로 공시되는 경우가 많음 → 절대값
            vals = {y: abs(v) for y, v in vals.items()}
        if vals:
            amounts[key] = vals
    return FinancialData(title=title, url=url, basis=basis, unit=unit, years=years, amounts=amounts,
                         unmapped_note=f"매핑되지 않은 계정: {', '.join(missing)}" if missing else "", unmapped=missing)


# ---------------- 지표 계산 ----------------
def _ratio(a: float | None, b: float | None, mult: float = 100.0) -> float | None:
    if a is None or b in (None, 0):
        return None
    return a / b * mult


def _growth(fd: FinancialData, key: str, y: int) -> float | None:
    a, b = fd.get(key, y), fd.get(key, y - 1)
    if a is None or b in (None, 0):
        return None
    return (a - b) / abs(b) * 100


def metric_values(fd: FinancialData, m: dict) -> dict[int, float | None]:
    kind = m["kind"]
    out: dict[int, float | None] = {}
    for y in fd.years:
        if kind == "ratio":
            den = fd.get(m["den"], y)
            # 분모가 음수면 해석이 뒤집히는 지표(예: 순손실 연도의 현금흐름/순이익)는 계산하지 않음
            v = None if m.get("positive_den") and (den is None or den <= 0) else _ratio(fd.get(m["num"], y), den)
        elif kind == "days":
            v = _ratio(fd.get(m["num"], y), fd.get(m["den"], y), 365.0)
        elif kind == "growth_gap":
            ga, gb = _growth(fd, m["num"], y), _growth(fd, m["den"], y)
            v = None if ga is None or gb is None else ga - gb
        else:
            raise ValueError(f"알 수 없는 지표 유형: {kind}")
        out[y] = None if v is None else round(v, 1)
    return out


def _formula(m: dict) -> str:
    a, b = ACCOUNT_LABEL[m["num"]], ACCOUNT_LABEL[m["den"]]
    return {"ratio": f"{a} ÷ {b} × 100", "days": f"{a} ÷ {b} × 365 (기말잔액 기준)",
            "growth_gap": f"{a} 증가율 − {b} 증가율"}[m["kind"]]


def _fmt(v: float | None, unit: str) -> str:
    return "N/A" if v is None else f"{v:,.1f}{unit}"


def evaluate_metric(fd: FinancialData, m: dict, risk_id: str | None) -> FinancialSignal:
    unit = {"ratio": "%", "days": "일", "growth_gap": "%p"}[m["kind"]]
    values = metric_values(fd, m)
    cur_y, prev_y = fd.years[-1], fd.years[-2]
    cur, prev = values.get(cur_y), values.get(prev_y)
    sig = m.get("signal", {})
    s = FinancialSignal(risk_id=risk_id, metric=m["name"], unit=unit, values=values,
                        accounts=[ACCOUNT_LABEL[m["num"]], ACCOUNT_LABEL[m["den"]]],
                        threshold=sig.get("threshold"), direction=sig.get("direction", "both"),
                        formula=_formula(m))
    a, pa = fd.get(m["num"], cur_y), fd.get(m["num"], prev_y)
    d, pd_ = fd.get(m["den"], cur_y), fd.get(m["den"], prev_y)
    if None not in (a, pa, d) and pd_ not in (None, 0):
        s.expected = round(pa * d / pd_, 1)
        s.amount_change, s.amount_account = round(a - s.expected, 1), ACCOUNT_LABEL[m["num"]]
    if m["kind"] == "growth_gap":
        # 증가율 격차는 그 자체가 신호 값 (최근 연도 기준)
        s.change = cur
        hit = cur is not None and s.threshold is not None and (
            (s.direction != "down" and cur >= s.threshold) or (s.direction != "up" and cur <= -s.threshold))
    else:
        if cur is None or prev is None:
            s.note = "계산에 필요한 계정이 공시에서 확인되지 않음"
            return s
        s.change = round(cur - prev, 1)
        hit = s.threshold is not None and (
            (s.direction != "down" and s.change >= s.threshold) or
            (s.direction != "up" and s.change <= -s.threshold))
    if cur is None:
        s.note = "계산에 필요한 계정이 공시에서 확인되지 않음"
        return s
    s.triggered = bool(hit)
    if s.triggered and m.get("question"):
        s.question = m["question"].format(
            prev=_fmt(prev, unit), cur=_fmt(cur, unit), prev_year=prev_y, cur_year=cur_y,
            change=f"{s.change:+,.1f}{'%p' if unit == '%' else unit}")
    return s


OVERVIEW_METRICS = [
    {"name": "영업이익률", "kind": "ratio", "num": "operating_income", "den": "revenue"},
    {"name": "부채비율", "kind": "ratio", "num": "total_liabilities", "den": "total_equity"},
    {"name": "영업현금흐름 ÷ 당기순이익", "kind": "ratio", "num": "cfo", "den": "net_income",
     "positive_den": True, "signal": {"threshold": 50, "direction": "down"},
     "question": "영업현금흐름 ÷ 당기순이익이 {prev}에서 {cur}로 낮아졌다({cur_year}년). "
                 "이익과 현금흐름의 차이를 만든 운전자본 항목(매출채권·계약자산·재고 등)은 무엇인가?"},
]


def evaluate(fd: FinancialData, risk_ids: list[str]) -> list[FinancialSignal]:
    out = [evaluate_metric(fd, m, None) for m in OVERVIEW_METRICS]
    defs = kb.metric_definitions()
    for rid in risk_ids:
        out += [evaluate_metric(fd, m, rid) for m in defs.get(rid, [])]
    return out


def chart_frame(fd: FinancialData, keys: list[str]) -> list[dict]:
    """차트용 long-format 행 (연도, 계정, 금액)."""
    return [{"연도": str(y), "계정": ACCOUNT_LABEL[k], "금액": fd.get(k, y)}
            for k in keys for y in fd.years if fd.get(k, y) is not None]


def metric_frame(s: FinancialSignal) -> list[dict]:
    last = max(s.values)
    return [{"연도": str(y), "값": v, "구분": "확인 신호" if (s.triggered and y == last) else "추이"}
            for y, v in s.values.items() if v is not None]


# ---------------- 계속기업 지표판 (수준 판정) ----------------
# 전년 대비 '변동'이 아니라 '수준'을 본다. 정보가 없으면 '정상'이 아니라 '확인 필요'.
Level = Literal["정상", "주의", "위험", "확인 필요"]


class LevelCheck(BaseModel):
    item: str
    level: Level
    value: str
    reason: str


def going_concern_checks(fd: FinancialData, th: dict) -> list[LevelCheck]:
    """감사기준서 570의 '재무적 사건·상황' 예시에 대응하는 4개 항목. 항상 4개, 순서 고정."""
    y, py = fd.years[-1], fd.years[-2]
    eq, cap, liab = fd.get("total_equity", y), fd.get("capital_stock", y), fd.get("total_liabilities", y)
    out: list[LevelCheck] = []

    # 1) 자본잠식
    if eq is None:
        out.append(LevelCheck(item="자본잠식", level="확인 필요", value="N/A", reason="자본총계를 공시에서 찾지 못함"))
    elif eq <= 0:
        out.append(LevelCheck(item="자본잠식", level="위험", value="완전잠식", reason=f"자본총계 {eq:,.0f}{fd.unit} (0 이하)"))
    elif cap is None:
        out.append(LevelCheck(item="자본잠식", level="확인 필요", value="N/A", reason="자본금을 찾지 못해 부분잠식 여부 판단 불가"))
    elif eq < cap:
        out.append(LevelCheck(item="자본잠식", level="주의", value="부분잠식",
                              reason=f"자본총계 {eq:,.0f} < 자본금 {cap:,.0f}{fd.unit}"))
    else:
        out.append(LevelCheck(item="자본잠식", level="정상", value="해당 없음",
                              reason=f"자본총계 {eq:,.0f} ≥ 자본금 {cap:,.0f}{fd.unit}"))

    # 2) 부채비율
    if eq is None or liab is None:
        out.append(LevelCheck(item="부채비율", level="확인 필요", value="N/A", reason="부채총계·자본총계 중 누락"))
    elif eq <= 0:
        out.append(LevelCheck(item="부채비율", level="확인 필요", value="N/A", reason="자본총계가 0 이하라 비율 해석 불가"))
    else:
        r = liab / eq * 100
        lv = "위험" if r >= th["debt_danger"] else "주의" if r >= th["debt_warn"] else "정상"
        out.append(LevelCheck(item="부채비율", level=lv, value=f"{r:,.1f}%",
                              reason=f"기준 주의 {th['debt_warn']}% / 위험 {th['debt_danger']}%"))

    # 3) 영업손익, 4) 영업활동현금흐름 — 당기 음수면 주의, 2년 연속이면 위험
    for key, item in (("operating_income", "영업손익"), ("cfo", "영업활동현금흐름")):
        cur, prev = fd.get(key, y), fd.get(key, py)
        if cur is None:
            out.append(LevelCheck(item=item, level="확인 필요", value="N/A", reason=f"{item}을 공시에서 찾지 못함"))
        elif cur < 0 and prev is not None and prev < 0:
            out.append(LevelCheck(item=item, level="위험", value=f"{cur:,.0f}{fd.unit}", reason=f"{py}·{y}년 2년 연속 음수"))
        elif cur < 0:
            out.append(LevelCheck(item=item, level="주의", value=f"{cur:,.0f}{fd.unit}", reason=f"{y}년 음수"))
        else:
            out.append(LevelCheck(item=item, level="정상", value=f"{cur:,.0f}{fd.unit}", reason=f"{y}년 0 이상"))
    return out
