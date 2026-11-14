"""재무 신호 — 비율·회전일수·증가율 격차 계산, 방향별 기준, 계정 누락 처리, DART 원본 매핑(단위·괄호 음수)."""

from scanner import collect
from scanner.analyze import OfflineAnalyzer
from scanner.brief import to_markdown
from scanner.finance import FinancialData, evaluate_metric, from_dart_rows
from scanner.pipeline import run


def _fd(**amounts):
    return FinancialData(title="t", years=[2023, 2024, 2025],
                         amounts={k: dict(zip([2023, 2024, 2025], v)) for k, v in amounts.items()})


def test_ratio_signal_and_question():
    fd = _fd(contract_assets=[150, 160, 240], revenue=[1000, 1000, 1000])
    m = {"name": "계약자산 ÷ 매출", "kind": "ratio", "num": "contract_assets", "den": "revenue",
         "signal": {"threshold": 5, "direction": "up"}, "question": "{prev}→{cur} ({change})"}
    s = evaluate_metric(fd, m, "X")
    assert s.values == {2023: 15.0, 2024: 16.0, 2025: 24.0}
    assert s.triggered and s.question == "16.0%→24.0% (+8.0%p)"


def test_direction_respected():
    fd = _fd(cogs=[900, 900, 850], revenue=[1000, 1000, 1000])
    m = {"name": "원가율", "kind": "ratio", "num": "cogs", "den": "revenue", "signal": {"threshold": 3, "direction": "up"}}
    assert not evaluate_metric(fd, m, "X").triggered          # 5%p 하락이지만 상승 방향만 감시


def test_missing_account_is_not_a_signal():
    fd = _fd(revenue=[1000, 1000, 1000])
    m = {"name": "재고", "kind": "days", "num": "inventory", "den": "cogs", "signal": {"threshold": 1}}
    s = evaluate_metric(fd, m, "X")
    assert not s.triggered and s.note


def test_growth_gap():
    fd = _fd(receivables=[100, 100, 130], revenue=[1000, 1000, 1050])
    m = {"name": "gap", "kind": "growth_gap", "num": "receivables", "den": "revenue", "signal": {"threshold": 15, "direction": "up"}}
    s = evaluate_metric(fd, m, "X")
    assert s.values[2025] == 25.0 and s.triggered


def test_dart_rows_mapping_and_scaling():
    rows = [
        {"account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "300,000,000,000",
         "frmtrm_amount": "200,000,000,000", "bfefrmtrm_amount": "100,000,000,000"},
        {"account_id": "-표준계정코드 미사용-", "account_nm": "재고 자산", "thstrm_amount": "10,000,000,000",
         "frmtrm_amount": "", "bfefrmtrm_amount": "-"},
        {"account_id": "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
         "account_nm": "유형자산의 취득", "thstrm_amount": "(5,000,000,000)"},
    ]
    fd = from_dart_rows(rows, 2025, "t", "", "연결")
    assert fd.amounts["revenue"] == {2025: 3000.0, 2024: 2000.0, 2023: 1000.0}
    assert fd.amounts["inventory"] == {2025: 100.0}          # 공백 다른 계정명도 매칭, 빈값 제외
    assert fd.amounts["capex"] == {2025: 50.0}               # 괄호 음수 → 절대값
    assert "매출원가" in fd.unmapped_note


def test_demo_financial_signals_attached_to_risks():
    docs, meta = collect.load_demo(collect.list_demos()["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, OfflineAnalyzer(), save=False, financials=meta["financials"])
    r1 = next(k for k in r.risks if k.risk_id == "CON-R1")
    assert any(s.triggered for s in r1.fin_signals)
    assert any(q.origin == "FIN" and "23.9%" in q.question for q in r1.questions)
    assert "Financial Signals" in to_markdown(r)
