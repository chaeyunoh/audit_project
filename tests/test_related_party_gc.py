"""특수관계자 교차점검(550)과 계속기업 지표판(570) — 정상·경계·예외."""
from decimal import Decimal

from scanner import collect
from scanner.analyze import OfflineAnalyzer
from scanner.finance import FinancialData, going_concern_checks
from scanner.pipeline import run
from scanner.related_party import amount_won, build_extraction, cross_check, questions, verify

SRC = "(단위: 백만원)\nA(주) | 계열회사 | 자금대여 | 12,000\nB(주) | 관계기업 | 매출 | 3,400"
ROW_A = {"related_party": "A(주)", "relationship": "계열회사", "transaction_type": "자금대여",
         "amount": "12,000", "quote": "A(주) | 계열회사 | 자금대여 | 12,000"}


# ---------- 인용 검증 ----------
def test_verify_keeps_grounded_and_drops_bad_rows():
    bad_quote = {**ROW_A, "related_party": "C(주)", "quote": "C(주) | 자금대여 | 1"}
    outside = {**ROW_A, "amount": "120,000"}                       # 인용문 밖의 금액
    missing = {**ROW_A, "transaction_type": ""}
    items, dropped = verify([ROW_A, bad_quote, outside, missing, "not a dict"], SRC, "S9")
    assert [i.related_party for i in items] == ["A(주)"]
    assert [d["reason"] for d in dropped] == ["인용문이 원문에 없음", "인용문 밖의 값(금액)",
                                              "필수 필드 누락", "형식 오류"]


def test_extraction_status():
    assert build_extraction("x", None, None, None, "-").status == "no_source"
    assert build_extraction("x", "S9", SRC, None, "-").status == "not_run"
    assert build_extraction("x", "S9", SRC, [], "AI").status == "ok"          # 거래 없음도 정상 응답
    assert build_extraction("x", "S9", SRC, [{"quote": "없는 문장", "related_party": "Z",
                                              "transaction_type": "대여"}], "AI").status == "failed"


# ---------- 금액 단위 ----------
def test_amount_units():
    assert amount_won("4,200", "억원") == amount_won("420,000", "백만원") == Decimal(420_000_000_000)
    assert amount_won("12 억원") == Decimal(1_200_000_000)
    assert amount_won("약 12억") is None                              # 해석 불가 → 비교하지 않음
    assert amount_won("12,000") is None                               # 단위 모르면 None


# ---------- 교차 비교 ----------
def _ex(rows, sid):
    return build_extraction(sid, sid, "\n".join(r["quote"] for r in rows), rows, "AI")


def test_cross_check_finds_each_kind_once():
    biz = [ROW_A, {**ROW_A, "transaction_type": "지급보증", "amount": "85,000",
                   "quote": "A(주) | 계열회사 | 지급보증 | 85,000"}]
    notes = [{**ROW_A, "relationship": "관계기업", "quote": "A(주) | 관계기업 | 자금대여 | 12,000"},
             {**ROW_A, "relationship": "관계기업", "transaction_type": "지급보증", "amount": "58,000",
              "quote": "A(주) | 관계기업 | 지급보증 | 58,000"},
             {"related_party": "B(주)", "relationship": "", "transaction_type": "매출", "amount": "3,400",
              "quote": "B(주) | 매출 | 3,400"}]
    r = cross_check(_ex(biz, "S1"), _ex(notes, "S2"), "백만원", "백만원")
    issues = [d.issue for d in r.discrepancies]
    assert sum("관계 기재" in i for i in issues) == 1                  # 거래상대방당 한 번
    assert sum("금액이 두 기재에서 다름" in i for i in issues) == 1     # 85,000 vs 58,000
    assert sum("B(주)" in i and "사업보고서" in i for i in issues) == 1  # 한쪽에만 있는 거래
    assert r.conclusive


def test_same_amount_different_units_is_not_a_discrepancy():
    biz = [{**ROW_A, "amount": "120", "quote": "A(주) | 계열회사 | 자금대여 | 120"}]
    notes = [{**ROW_A, "amount": "12,000", "quote": "A(주) | 계열회사 | 자금대여 | 12,000"}]
    assert cross_check(_ex(biz, "S1"), _ex(notes, "S2"), "억원", "백만원").discrepancies == []


def test_missing_side_is_not_reported_as_clean():
    r = cross_check(build_extraction("사업보고서", "S1", SRC, [ROW_A], "AI"),
                    build_extraction("주석", None, None, None, "-"))
    assert r.discrepancies == [] and not r.conclusive
    assert any("확인하지 못했다" in q for q in questions(r))         # '불일치 없음'이 아니라 '확인 필요'


# ---------- 계속기업 지표판 ----------
TH = {"debt_warn": 200, "debt_danger": 400}


def _fd(**a):
    return FinancialData(title="t", years=[2024, 2025], amounts={k: dict(zip([2024, 2025], v)) for k, v in a.items()})


def test_going_concern_levels():
    fd = _fd(total_equity=[100, -5], capital_stock=[50, 50], total_liabilities=[300, 500],
             operating_income=[-10, -20], cfo=[5, -1])
    got = {c.item: c.level for c in going_concern_checks(fd, TH)}
    assert got == {"자본잠식": "위험", "부채비율": "확인 필요", "영업손익": "위험", "영업활동현금흐름": "주의"}


def test_going_concern_boundary_and_partial_impairment():
    fd = _fd(total_equity=[100, 40], capital_stock=[50, 50], total_liabilities=[80, 80],
             operating_income=[1, 0], cfo=[1, 1])
    got = {c.item: c.level for c in going_concern_checks(fd, TH)}
    assert got["자본잠식"] == "주의" and got["부채비율"] == "주의"      # 80/40 = 200% → 기준 이상이면 해당 수준
    assert got["영업손익"] == "정상"                                   # 0은 손실 아님


def test_going_concern_missing_data_is_never_normal():
    got = going_concern_checks(_fd(revenue=[1, 1]), TH)
    assert len(got) == 4 and {c.level for c in got} == {"확인 필요"}


# ---------- 파이프라인 연결 ----------
def test_demo_triggers_gc_and_rpt_questions():
    docs, meta = collect.load_demo(collect.list_demos()["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, OfflineAnalyzer(), save=False, financials=meta["financials"],
            engagement="초도감사")
    ids = [k.risk_id for k in r.risks]
    assert "G-GC" in ids and "G-OB" in ids
    g_rp = next(k for k in r.risks if k.risk_id == "G-RP")
    assert any(q.origin == "XCHK" and "지급보증" in q.question for q in g_rp.questions)
    assert r.rpt.business.origin == "데모 고정 응답"


def test_healthy_demo_has_no_gc_area():
    docs, meta = collect.load_demo(collect.list_demos()["다라반도체(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, OfflineAnalyzer(), save=False, financials=meta["financials"])
    assert "G-GC" not in [k.risk_id for k in r.risks] and "G-OB" not in [k.risk_id for k in r.risks]
    assert r.rpt.conclusive and r.rpt.discrepancies == []
