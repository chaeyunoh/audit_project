"""계획 중요성(감사기준서 320) — 계산, 기준 제안, 신호·불일치 금액 비교."""
from scanner import collect
from scanner.analyze import OfflineAnalyzer
from scanner.finance import FinancialData, evaluate_metric
from scanner.materiality import classify, compute, discrepancy_levels, signal_levels, suggest
from scanner.pipeline import run


def _fd(**a):
    return FinancialData(title="t", years=[2024, 2025], unit="억원",
                         amounts={k: dict(zip([2024, 2025], v)) for k, v in a.items()})


# ---------- 계산 ----------
def test_compute_overall_performance_trivial():
    m = compute(_fd(pretax_income=[900, 1000]), "pretax_income", pct=5, perf_pct=75, trivial_pct=5)
    assert (m.base, m.overall, m.performance, m.trivial) == (1000, 50.0, 37.5, 2.5)
    assert m.year == 2025 and m.ok


def test_compute_rejects_non_positive_or_missing_base():
    loss = compute(_fd(pretax_income=[100, -30]), "pretax_income", 5, 75, 5)
    assert not loss.ok and "0 이하" in loss.note
    missing = compute(_fd(revenue=[1, 1]), "total_assets", 1, 75, 5)
    assert not missing.ok and "찾지 못" in missing.note


# ---------- 기준 제안 (결정은 감사인) ----------
def test_suggest_pretax_when_stable():
    key, why = suggest(_fd(pretax_income=[950, 1000], revenue=[20000, 21000]))
    assert key == "pretax_income" and why


def test_suggest_revenue_when_pretax_is_loss_or_volatile():
    assert suggest(_fd(pretax_income=[500, -20], revenue=[9000, 9500]))[0] == "revenue"
    assert suggest(_fd(pretax_income=[1300, 560], revenue=[43500, 45200]))[0] == "revenue"  # 57% 감소


def test_suggest_lower_performance_pct_when_risk_is_higher():
    _, why_normal, perf_normal = suggest(_fd(pretax_income=[950, 1000]), with_perf=True)
    _, why_risky, perf_risky = suggest(_fd(pretax_income=[950, 1000]), with_perf=True, higher_risk=True)
    assert (perf_normal, perf_risky) == (75, 50) and why_risky != why_normal


# ---------- 비교 ----------
def test_classify_boundaries_use_greater_or_equal():
    m = compute(_fd(pretax_income=[1000, 1000]), "pretax_income", 5, 75, 5)  # 50 / 37.5 / 2.5
    assert classify(50, m) == "계획 중요성 이상"
    assert classify(-37.5, m) == "수행 중요성 이상"                       # 방향 무관, 절대값
    assert classify(2.5, m) == "명백히 사소한 금액 초과"
    assert classify(2.4, m) == "명백히 사소함"
    assert classify(None, m) is None


def test_signal_amount_is_gap_from_expectation_not_raw_change():
    # 기대치 = 전년 계약자산 7,100 × (당기 매출 45,200 ÷ 전년 매출 43,500) = 7,377.5
    fd = _fd(contract_assets=[7100, 10800], revenue=[43500, 45200])
    s = evaluate_metric(fd, {"name": "계약자산 ÷ 매출", "kind": "ratio", "num": "contract_assets",
                             "den": "revenue", "signal": {"threshold": 5}}, "X")
    assert s.expected == 7377.5 and s.amount_change == 3422.5 and s.amount_account == "계약자산"


def test_ratio_unchanged_means_no_gap_even_if_account_grew():
    # 매출과 원가가 같은 비율로 늘면 원가가 크게 늘어도 기대치 대비 차이는 0
    fd = _fd(cogs=[9000, 18000], revenue=[10000, 20000])
    s = evaluate_metric(fd, {"name": "원가율", "kind": "ratio", "num": "cogs", "den": "revenue"}, "X")
    assert s.amount_change == 0


def test_signal_and_discrepancy_levels():
    docs, meta = collect.load_demo(collect.list_demos()["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, OfflineAnalyzer(), save=False, financials=meta["financials"])
    m = r.materiality
    assert m and m.ok and m.benchmark == "revenue"          # 데모 세전이익이 크게 줄어 매출 기준 제안
    lv = signal_levels(r, m)
    ca = next(s for k in r.risks for s in k.fin_signals if s.metric == "계약자산 ÷ 매출")
    assert lv[id(ca)] == "계획 중요성 이상"                  # 계약자산 +3,700억원
    # 지급보증 85,000 vs 58,000 백만원 → 차이 270억원
    gaps = discrepancy_levels(r, m)
    gp = next(d for d in r.rpt.discrepancies if "금액" in d.issue)
    assert gp.gap_won == 27_000_000_000 and gaps[id(gp)] in ("수행 중요성 이상", "명백히 사소한 금액 초과")
