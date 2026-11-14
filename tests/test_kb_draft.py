"""산업 초안 생성기 — KAM 파싱, 참고자료, 조립·검증·저장."""
import pytest

from scanner import kam, kb, kb_draft
from scanner.finance import FinancialData

SAMSUNG_LIKE = """<P>핵심감사사항</P><P>핵심감사사항은 우리의 전문가적 판단에 따라 당기 재무제표 감사에서 가장 유의적인 사항들입니다.</P>
<P>건설중인자산의 감가상각개시시점 평가</P><P>핵심감사사항으로 결정한 이유</P><P>사용가능시점 결정에 경영진 판단이 필요합니다.</P>
<P>핵심감사사항이 감사에서 다루어진 방법</P><P>상기의 핵심감사사항에 대응하기 위해 우리가 수행한 주요 감사절차는 다음과 같습니다.</P>
<P>- 사용가능시점 판단에 대한 내부통제의 이해</P><P>- 감가상각 개시 승인 통제의 효과성 평가- 장기 미대체 건설중인자산 모니터링 평가</P>
<P>판매장려활동에 대한 매출차감의 정확성</P><P>핵심감사사항으로 결정한 이유</P><P>장려금 추정에 판단이 수반됩니다.</P>
<P>핵심감사사항이 감사에서 다루어진 방법</P><P>- 매출차감 정책의 승인 통제 평가</P><P>- 기말 추정치와 사후 정산 금액 비교</P>
<P>재무제표에 대한 경영진과 지배기구의 책임</P>"""


def test_parse_filing_titles_reasons_procedures():
    got = kam.parse_filing(SAMSUNG_LIKE * 2)                          # 연결·별도 두 번 나와도 한 번만
    assert [k.title for k in got] == ["건설중인자산의 감가상각개시시점 평가", "판매장려활동에 대한 매출차감의 정확성"]
    assert "경영진 판단" in got[0].why
    assert got[0].procedures == ["사용가능시점 판단에 대한 내부통제의 이해", "감가상각 개시 승인 통제의 효과성 평가",
                                 "장기 미대체 건설중인자산 모니터링 평가"]
    assert got[1].procedures[-1] == "기말 추정치와 사후 정산 금액 비교"


def test_titles_from_api_uses_current_year_only():
    rows = [{"bsns_year": "제57기 (당기)", "adtor": "삼정회계법인", "core_adt_matter": "1. A 평가\n2. B 정확성"},
            {"bsns_year": "제56기 (전기)", "adtor": "삼정회계법인", "core_adt_matter": "1. 옛 사항"}]
    assert kam.titles_from_api(rows) == (["A 평가", "B 정확성"], "삼정회계법인")


def test_split_titles_joins_wrapped_lines():
    # 실제 API 응답 형태 (한화생명·미래에셋생명·삼성전자)
    assert kam.split_titles("1) 위험률 가정\n2) 배분 전 보험계약마진 중 당기에 제공된\n보장단위로 배분된 비율") == \
        ["위험률 가정", "배분 전 보험계약마진 중 당기에 제공된 보장단위로 배분된 비율"]
    assert kam.split_titles("보험계약 이행현금흐름 산출 시 적용된\n손해율 가정") == ["보험계약 이행현금흐름 산출 시 적용된 손해율 가정"]
    assert kam.split_titles("수익인식\n재고자산 평가") == ["수익인식", "재고자산 평가"]


def test_merge_keeps_api_titles_even_without_parsed_body():
    got = kam.merge(["A 평가", "없는 사항"], [kam.KAM(title="A 평가", why="이유", procedures=["절차"])])
    assert got[0].why == "이유" and got[1].title == "없는 사항" and not got[1].procedures


# ---------- 참고자료 ----------
def _src(name, text, **amounts):
    fd = FinancialData(title="t", years=[2023, 2024, 2025],
                       amounts={k: dict(zip([2023, 2024, 2025], v)) for k, v in amounts.items()}) if amounts else None
    return kb_draft.CompanySource(corp_name=name, corp_code="0", induty_code="65", business=text, financials=fd)


def test_keyword_candidates_need_two_companies():
    srcs = [_src("A", "보험계약마진 보험계약마진 해약환급금 독자표현"), _src("B", "보험계약마진 해약환급금")]
    words = [w for w, _, _ in kb_draft.keyword_candidates(srcs)]
    assert "보험계약마진" in words and "해약환급금" in words and "독자표현" not in words


def test_metric_profile_suggests_threshold_with_floor():
    srcs = [_src("A", "", cogs=[90, 93, 96], revenue=[100, 100, 100]),        # 원가율 변동 3, 3
            _src("B", "", cogs=[80, 84, 88], revenue=[100, 100, 100])]        # 변동 4, 4
    row = next(r for r in kb_draft.metric_profile(srcs) if r["key"] == "cogs_ratio")
    assert row["최근값"] == {"A": 96.0, "B": 88.0} and row["제안 기준"] == 4   # |변동| [3,3,4,4]의 75% 분위
    outlier = [_src("A", "", cogs=[90, 91, 99], revenue=[100, 100, 100]),     # 변동 1, 8 — 이상치 하나가
               _src("B", "", cogs=[80, 80, 81], revenue=[100, 100, 100])]     # 기준을 끌어올리지 않는다
    assert next(r for r in kb_draft.metric_profile(outlier) if r["key"] == "cogs_ratio")["제안 기준"] == 2
    tiny = [_src("C", "", cogs=[50, 50, 50], revenue=[100, 100, 100])]
    assert next(r for r in kb_draft.metric_profile(tiny) if r["key"] == "cogs_ratio")["제안 기준"] == 2  # 하한


# ---------- 조립 · 검증 ----------
def _raw(stage="인수", icon="contract", assertions=("평가와배분",), src=("K01",), metric=""):
    return {"summary": "요약", "business_model": ["보험료를 받는다"], "value_chain": ["판매", "인수"],
            "stakeholders": ["계약자"], "detect_keywords": ["보험계약마진"],
            "stage_info": [{"stage": "판매", "icon": "sell", "do": "d", "money": "m", "books": "b"},
                           {"stage": "인수", "icon": icon, "do": "d", "money": "m", "books": "b"}],
            "traits": [{"name": "CSM", "stage": stage, "detect_keywords": ["CSM"], "source_ids": list(src),
                        "risks": [{"title": "CSM 측정", "potential_risk": "확인 필요성이 존재", "accounts": ["보험계약부채"],
                                   "assertions": list(assertions), "references": ["K-IFRS 제1117호"],
                                   "evidence_docs": ["계리 보고서"], "priority": 1, "questions": ["가정은?"],
                                   "metric": metric, "source_ids": list(src)}]}]}


IDS = {"K01": "A사 핵심감사사항: CSM", "B1-01": "A사 사업의 내용"}
KAMS = [kam.KAM(title="CSM", company="A사"), kam.KAM(title="손해율", company="B사")]


def test_assemble_assigns_ids_metrics_and_reports_missed_kam():
    block, notes = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], _raw(metric="ar_days"),
                                     [{"key": "ar_days", "제안 기준": 17}], IDS, KAMS)
    r = block["traits"][0]["risks"][0]
    assert block["traits"][0]["trait_id"] == "INSX-T1" and r["risk_id"] == "INSX-R1"
    assert r["metrics"][0]["signal"]["threshold"] == 17 and r["metrics"][0]["num"] == "receivables"
    assert r["sources"] == ["A사 핵심감사사항: CSM"] and block["review"]["status"] == "draft"
    assert any("손해율" in n for n in notes)                         # 반영 안 된 KAM을 알린다
    assert kb_draft.validate("insurance_x", block) == []


def test_assemble_drops_unsourced_risks():
    block, notes = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], _raw(src=("K99",)), [], IDS, KAMS)
    assert block["traits"] == [] and any("없는 출처" in n for n in notes)
    assert "산업 특성이 없음" in kb_draft.validate("insurance_x", block)


@pytest.mark.parametrize("raw,needle", [
    (_raw(stage="없는단계"), "가치사슬에 없음"),
    (_raw(icon="nope"), "없는 그림"),
    (_raw(assertions=("아무주장",)), "용어집"),
])
def test_validate_rejects_rule_violations(raw, needle):
    block, _ = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], raw, [], IDS, KAMS)
    assert any(needle in e for e in kb_draft.validate("insurance_x", block))


def test_validate_rejects_existing_key_and_ksic_clash():
    block, _ = kb_draft.assemble("construction", "x", "INSX", ["41"], _raw(), [], IDS, KAMS)
    errs = kb_draft.validate("construction", block)
    assert any("이미 있는 산업 키" in e for e in errs) and any("겹침" in e for e in errs)


# ---------- 저장 → 지식베이스에 '초안'으로 합류 ----------
def test_save_then_kb_loads_as_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "DRAFT_DIR", tmp_path)
    monkeypatch.setattr(kb_draft, "DRAFT_DIR", tmp_path)
    kb.load_kb.cache_clear()
    try:
        block, _ = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], _raw(), [], IDS, KAMS)
        block["review"]["status"] = "reviewed"                       # 저장 파일을 고쳐도 초안으로만 합류
        kb_draft.save("insurance_x", block)
        assert "insurance_x" in kb.industries() and kb.is_draft_file("insurance_x")
        assert kb.industries()["insurance_x"]["review"]["status"] == "draft"
        assert kb.industry_from_ksic("65110") == "insurance_x"
        with pytest.raises(ValueError):
            kb_draft.save("insurance_x", block)                     # 같은 키 두 번 저장 불가
    finally:
        kb.load_kb.cache_clear()


def test_draft_cannot_override_existing_industry(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "DRAFT_DIR", tmp_path)
    (tmp_path / "x.yaml").write_text("construction:\n  name: 가짜\n", encoding="utf-8")
    kb.load_kb.cache_clear()
    try:
        assert kb.industries()["construction"]["name"] == "건설업"
    finally:
        kb.load_kb.cache_clear()
