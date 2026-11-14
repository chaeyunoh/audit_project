"""실제 공시(삼성전자·LG에너지솔루션·카카오·신세계) 실행에서 발견한 문제의 회귀 테스트."""
from scanner import collect, kb
from scanner.analyze import OfflineAnalyzer
from scanner.models import ClaimType, SourceDoc
from scanner.pipeline import run
from scanner.related_party import build_extraction, cross_check, questions

ROW = {"related_party": "A(주)", "relationship": "계열회사", "transaction_type": "매출", "amount": "100",
       "quote": "A(주) | 계열회사 | 매출 | 100"}
ONLY_BIZ = {"related_party": "B(주)", "relationship": "계열회사", "transaction_type": "매입", "amount": "5",
            "quote": "B(주) | 계열회사 | 매입 | 5"}


def _ex(rows, sid, truncated=False):
    return build_extraction(sid, sid, "\n".join(r["quote"] for r in rows), rows, "AI", truncated=truncated)


# ---------- 특수관계자 주석이 잘린 경우 ----------
def test_truncated_notes_do_not_produce_missing_party_discrepancy():
    r = cross_check(_ex([ROW, ONLY_BIZ], "S03"), _ex([ROW], "S04", truncated=True))
    assert not any("B(주)" in d.issue for d in r.discrepancies)      # 잘린 뒷부분에 있을 수 있음
    assert not r.conclusive
    assert any("앞부분만" in q for q in questions(r))


def test_untruncated_notes_still_report_missing_party():
    r = cross_check(_ex([ROW, ONLY_BIZ], "S03"), _ex([ROW], "S04"))
    assert any("B(주)" in d.issue for d in r.discrepancies)


def test_rpt_sections_reports_truncation():
    body = "\n".join(f"C{i}(주) | 계열회사 | 매출 | {i}" for i in range(50))
    doc = f"<P>31. 우발부채</P><P>32. 특수관계자 거래</P><P>{body}</P><P>33. 보고기간 후 사건</P>"
    _, notes, cut = collect.DartCollector.rpt_sections(doc, limit=100)
    assert len(notes) == 100 and cut == {"business": False, "notes": True}


# ---------- 사업 구조 '사실'은 특수관계자 구간에서 뽑지 않는다 ----------
def _docs(extra_rpt_text):
    biz = "당사는 메모리 반도체를 설계하고 제조하여 판매합니다. " * 3
    return [SourceDoc(doc_id="S02", title="사업의 내용", publisher="DART", raw_text=biz),
            SourceDoc(doc_id="S04", title="특수관계자 주석", publisher="DART", raw_text=extra_rpt_text)]


def test_business_facts_never_come_from_rpt_section():
    rpt = "락금생활건강무역(상해)유한공사 등 반도체 매출 거래가 있습니다. 반도체 반도체 반도체 계열사 목록입니다."
    meta = {"induty_code": "26111", "rpt_docs": {"notes": "S04"}}
    r = run("t", _docs(rpt), meta, OfflineAnalyzer(), save=False)
    facts = [c for c in r.snapshot.business_model + r.snapshot.characteristics if c.claim_type == ClaimType.FACT]
    assert facts and all(all(s.startswith("S02") for s in c.source_ids) for c in facts)


# ---------- 업종코드가 지식베이스 밖이지만 같은 중분류 산업이 본문에서 압도적인 경우 ----------
def test_same_division_text_rule_applies_semiconductor_to_ksic_264():
    biz = "반도체 메모리 DRAM 낸드 파운드리 웨이퍼 " * 10              # 60회
    docs = [SourceDoc(doc_id="S02", title="사업의 내용", publisher="DART", raw_text=biz)]
    r = run("t", docs, {"induty_code": "264"}, OfflineAnalyzer(), save=False)
    assert r.snapshot.industry_key == "semiconductor"
    assert any("같은 중분류" in w for w in r.warnings)


def test_same_division_rule_needs_strong_evidence():
    docs = [SourceDoc(doc_id="S02", title="사업의 내용", publisher="DART", raw_text="통신장비 반도체 부품을 일부 사용합니다. " * 3)]
    r = run("t", docs, {"induty_code": "264"}, OfflineAnalyzer(), save=False)
    assert not kb.is_supported(r.snapshot.industry_key)               # 근거가 약하면 끼워 넣지 않음


# ---------- 수동 지정 산업은 결과에 드러나야 한다 ----------
def test_manual_industry_override_is_visible():
    docs, meta = collect.load_demo(collect.list_demos()["다라반도체(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, OfflineAnalyzer(), industry_key="construction", save=False)
    assert any("수동으로" in w and "건설업" in w for w in r.warnings)


# ---------- DART 오류 메시지에 인증키가 새지 않는다 ----------
def test_dart_network_errors_never_contain_the_api_key(monkeypatch):
    import pytest
    import requests

    from scanner.collect import CollectError, DartCollector

    secret = "a" * 40
    url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={secret}&rcept_no=1"
    for exc in (requests.ConnectTimeout(f"Max retries exceeded with url: {url}"),
                requests.ConnectionError(f"HTTPSConnectionPool: {url}")):
        def boom(*a, _e=exc, **k):
            raise _e
        monkeypatch.setattr(requests, "get", boom)
        with pytest.raises(CollectError) as info:
            DartCollector(secret)._get("document.xml", rcept_no="1")
        assert secret not in str(info.value) and info.value.__cause__ is None and info.value.__suppress_context__


# ---------- 첨부정정 공시는 본문이 없다 (현대제철 2025) ----------
def test_pick_annual_report_skips_attachment_only_corrections():
    from scanner.collect import pick_annual_report
    rows = [{"rcept_no": "3", "report_nm": "[첨부정정]사업보고서 (2025.12)"},
            {"rcept_no": "2", "report_nm": "[첨부정정]사업보고서 (2025.12)"},
            {"rcept_no": "1", "report_nm": "사업보고서 (2025.12)"}]
    assert pick_annual_report(rows)["rcept_no"] == "1"
    amended = [{"rcept_no": "9", "report_nm": "[기재정정]사업보고서 (2025.12)"}] + rows
    assert pick_annual_report(amended)["rcept_no"] == "9"          # 본문 전체 정정은 사용


def test_document_error_xml_becomes_readable_error(monkeypatch):
    import pytest

    from scanner.collect import CollectError, DartCollector
    body = '<?xml version="1.0"?><result><status>014</status><message>파일이 존재하지 않습니다.</message></result>'

    class R:
        content = body.encode("utf-8")
    monkeypatch.setattr(DartCollector, "_get", lambda self, *a, **k: R())
    with pytest.raises(CollectError, match=r"\[014\].*파일이 존재하지 않습니다"):
        DartCollector("k" * 40).document_text("1")
