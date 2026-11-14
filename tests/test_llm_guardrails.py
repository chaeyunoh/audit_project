"""Claude 분석기를 '일부러 잘못 답하는' 가짜 응답으로 대체해 가드레일이 막는지 확인."""
import json
from types import SimpleNamespace

from scanner import collect
from scanner.analyze import ClaudeAnalyzer
from scanner.models import ClaimType
from scanner.pipeline import run

BAD_ANALYSIS = {
    "business_model": [
        {"text": "2025년 말 수주잔고는 3조 2,450억원입니다", "claim_type": "FACT", "source_ids": ["S01-001"],
         "quote": "2025년 말 수주잔고는 3조 2,450억원입니다."},
        {"text": "수주잔고는 9조원이다", "claim_type": "FACT", "source_ids": ["S01-001"],
         "quote": "2025년 말 수주잔고는 3조 2,450억원입니다."},                                   # 수치 날조
        {"text": "해외 매출이 절반이다", "claim_type": "FACT", "source_ids": ["S07-001"], "quote": ""},  # 출처 날조
        {"text": "수주잔고가 업계 최고 수준이다", "claim_type": "FACT", "source_ids": ["S01-001"],
         "quote": "당사의 수주잔고는 업계 최고 수준입니다."},                                       # 인용 날조
    ],
    "value_chain": ["수주", "시공", "준공"],
    "stakeholders": [{"text": "시행사", "claim_type": "INFERENCE", "source_ids": ["S01-001"], "quote": ""}],
    "characteristics": [
        {"text": "이 회사는 위험하다", "claim_type": "INFERENCE", "source_ids": ["S01-001"], "quote": ""},   # 단정
    ],
    "detected_traits": [
        {"trait_id": "CON-PF", "rationale": "시행사의 PF 대출에 대해 책임준공 약정을 제공",
         "claim_type": "FACT", "source_ids": ["S01-001"],
         "quote": "시행사의 PF 대출에 대해 책임준공 약정을 제공하고 있으며"},
    ],
    "information_gaps": ["프로젝트별 원가율 자료 없음"],
}
BAD_QUESTIONS = {"items": [
    {"risk_id": "CON-R5", "question": "책임준공 약정 대상 사업장별 공정률은?", "purpose": "완전성",
     "source_ids": ["S01-001"]},
    {"risk_id": "CON-R5", "question": "우발부채 공시에 오류가 있다는 점을 알고 있는가?", "purpose": "",
     "source_ids": []},                                                                      # 단정 질문
]}


BAD_RPT = {"items": [
    {"related_party": "가나디벨롭먼트(주)", "relationship": "계열회사", "transaction_type": "자금대여",
     "amount": "12,000", "quote": "가나디벨롭먼트(주) | 계열회사 | 자금대여 | 12,000"},
    {"related_party": "유령회사(주)", "relationship": "", "transaction_type": "대여", "amount": "1",
     "quote": "유령회사(주) 대여 1"},                                                         # 인용 날조
]}


class FakeClient:
    """요청 스키마로 어떤 작업인지 구분해 미리 정한 (일부러 틀린) 응답을 돌려준다."""

    def __init__(self, fail_analysis: bool = False):
        self.fail_analysis = fail_analysis
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        schema = kw["output_config"]["format"]["schema"]
        assert kw["output_config"]["format"]["type"] == "json_schema"
        if "business_model" in schema["properties"]:
            if self.fail_analysis:
                return SimpleNamespace(stop_reason="max_tokens", content=[])
            body = BAD_ANALYSIS
        elif "related_party" in schema["properties"]["items"]["items"]["properties"]:
            body = BAD_RPT
        else:
            body = BAD_QUESTIONS
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(body))])


def _analyzer(**kw):
    import anthropic
    a = ClaudeAnalyzer.__new__(ClaudeAnalyzer)
    a.anthropic, a.client, a.model, a.effort = anthropic, FakeClient(**kw), "fake", "low"
    return a


def test_llm_output_is_controlled():
    a = _analyzer()

    docs, meta = collect.load_demo(collect.list_demos()["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, a, save=False)

    bm = {c.text: c for c in r.snapshot.business_model}
    assert bm["2025년 말 수주잔고는 3조 2,450억원입니다"].claim_type == ClaimType.FACT
    assert bm["수주잔고는 9조원이다"].claim_type == ClaimType.UNVERIFIED
    assert bm["해외 매출이 절반이다"].claim_type == ClaimType.UNVERIFIED
    assert bm["해외 매출이 절반이다"].source_ids == []
    assert bm["수주잔고가 업계 최고 수준이다"].claim_type == ClaimType.UNVERIFIED   # 원문에 없는 인용
    assert any("단정" in f for f in r.snapshot.characteristics[0].flags)

    pf = next(k for k in r.risks if k.risk_id == "CON-R5")
    ai_q = [q.question for q in pf.questions if q.origin == "AI"]
    assert ai_q == ["책임준공 약정 대상 사업장별 공정률은?"]
    assert {"CON-R1"}.isdisjoint({k.risk_id for k in r.risks})  # AI가 고르지 않은 특성은 매핑 안 됨


def test_rpt_hallucinated_row_dropped_in_llm_mode():
    docs, meta = collect.load_demo(collect.list_demos()["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, _analyzer(), save=False, financials=meta["financials"])
    assert r.rpt.business.origin == "AI"
    assert [x.related_party for x in r.rpt.business.items] == ["가나디벨롭먼트(주)"]
    assert r.rpt.business.dropped[0]["reason"] == "인용문이 원문에 없음"


def test_llm_failure_falls_back_instead_of_stopping():
    docs, meta = collect.load_demo(collect.list_demos()["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, _analyzer(fail_analysis=True), save=False)
    assert r.mode == "OFFLINE" and any("AI 분석 실패" in w for w in r.warnings)
    assert any(k.risk_id == "CON-R1" for k in r.risks)   # 기준선 결과는 그대로 나온다
