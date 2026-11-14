"""산업 초안 생성기 — 참고자료(용어 후보·지표 분포), 조립·검증·저장."""
import pytest

from scanner import kb, kb_draft
from scanner.finance import FinancialData


# ---------- 참고자료 ----------
def _src(name, text, **amounts):
    fd = FinancialData(title="t", years=[2023, 2024, 2025],
                       amounts={k: dict(zip([2023, 2024, 2025], v)) for k, v in amounts.items()}) if amounts else None
    return kb_draft.CompanySource(corp_name=name, corp_code="0", induty_code="65", business=text, financials=fd)


def test_keyword_candidates_need_two_companies():
    srcs = [_src("A", "보험계약마진 보험계약마진 해약환급금 독자표현"), _src("B", "보험계약마진 해약환급금")]
    words = [w for w, _, _ in kb_draft.keyword_candidates(srcs)]
    assert "보험계약마진" in words and "해약환급금" in words and "독자표현" not in words


def test_keyword_candidates_drop_table_noise():
    # 보험사처럼 사업의 내용이 표 위주일 때 나오던 표 머리글·각주
    srcs = [_src("A", "구분 현황 금액 주1 소계 생명보험"), _src("B", "구분 현황 금액 주1 소계 생명보험")]
    assert [w for w, _, _ in kb_draft.keyword_candidates(srcs)] == ["생명보험"]


def test_metric_profile_suggests_threshold_with_floor():
    srcs = [_src("A", "", cogs=[90, 93, 96], revenue=[100, 100, 100]),        # 원가율 변동 3, 3
            _src("B", "", cogs=[80, 84, 88], revenue=[100, 100, 100])]        # 변동 4, 4
    row = next(r for r in kb_draft.metric_profile(srcs) if r["key"] == "cogs_ratio")
    assert row["최근값"] == {"A": 96.0, "B": 88.0} and row["제안 기준"] == 4   # |변동| [3,3,4,4]의 75% 분위
    outlier = [_src("A", "", cogs=[90, 91, 99], revenue=[100, 100, 100]),     # 변동 1, 8 — 이상치 하나가
               _src("B", "", cogs=[80, 80, 81], revenue=[100, 100, 100])]     # 기준을 끌어올리지 않는다
    assert next(r for r in kb_draft.metric_profile(outlier) if r["key"] == "cogs_ratio")["제안 기준"] == 2


def test_source_blocks_use_business_sections_only():
    text, ids = kb_draft.source_blocks([_src("A사", "보험료를 받아 운용합니다. " * 200)])
    assert ids and all(k.startswith("B1-") for k in ids) and 'kind="business"' in text


def test_skeleton_prefills_keywords_and_thresholds():
    out = kb_draft.skeleton("life_x", "생명보험업", "LIF", ["6511"], [], [("생명보험", 2, 5)],
                            [{"지표": "매출채권 회전일수", "제안 기준": 12}])
    assert "detect_keywords: [생명보험]" in out and "매출채권 회전일수 12" in out and "LIF-T1" in out


# ---------- 조립 · 검증 ----------
def _raw(stage="인수", icon="contract", assertions=("평가와배분",), src=("B1-01",), metric=""):
    return {"summary": "요약", "business_model": ["보험료를 받는다"], "value_chain": ["판매", "인수"],
            "stakeholders": ["계약자"], "detect_keywords": ["보험계약마진"],
            "stage_info": [{"stage": "판매", "icon": "sell", "do": "d", "money": "m", "books": "b"},
                           {"stage": "인수", "icon": icon, "do": "d", "money": "m", "books": "b"}],
            "traits": [{"name": "CSM", "stage": stage, "detect_keywords": ["CSM"], "source_ids": list(src),
                        "risks": [{"title": "CSM 측정", "potential_risk": "확인 필요성이 존재", "accounts": ["보험계약부채"],
                                   "assertions": list(assertions), "references": ["K-IFRS 제1117호"],
                                   "evidence_docs": ["계리 보고서"], "priority": 1, "questions": ["가정은?"],
                                   "metric": metric, "source_ids": list(src)}]}]}


IDS = {"B1-01": "A사 사업의 내용"}


def test_assemble_assigns_ids_and_metrics():
    block, notes = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], _raw(metric="ar_days"),
                                     [{"key": "ar_days", "제안 기준": 17}], IDS)
    r = block["traits"][0]["risks"][0]
    assert block["traits"][0]["trait_id"] == "INSX-T1" and r["risk_id"] == "INSX-R1"
    assert r["metrics"][0]["signal"]["threshold"] == 17 and r["metrics"][0]["num"] == "receivables"
    assert r["sources"] == ["A사 사업의 내용"] and block["review"]["status"] == "draft"
    assert notes == [] and kb_draft.validate("insurance_x", block) == []


def test_assemble_drops_unsourced_risks():
    block, notes = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], _raw(src=("B9-99",)), [], IDS)
    assert block["traits"] == [] and any("없는 출처" in n for n in notes)
    assert "산업 특성이 없음" in kb_draft.validate("insurance_x", block)


@pytest.mark.parametrize("raw,needle", [
    (_raw(stage="없는단계"), "가치사슬에 없음"),
    (_raw(icon="nope"), "없는 그림"),
    (_raw(assertions=("아무주장",)), "용어집"),
])
def test_validate_rejects_rule_violations(raw, needle):
    block, _ = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], raw, [], IDS)
    assert any(needle in e for e in kb_draft.validate("insurance_x", block))


def test_validate_rejects_existing_key_and_ksic_clash():
    block, _ = kb_draft.assemble("construction", "x", "INSX", ["41"], _raw(), [], IDS)
    errs = kb_draft.validate("construction", block)
    assert any("이미 있는 산업 키" in e for e in errs) and any("겹침" in e for e in errs)


# ---------- 저장 → 지식베이스에 '초안'으로 합류 ----------
def test_save_then_kb_loads_as_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "DRAFT_DIR", tmp_path)
    monkeypatch.setattr(kb_draft, "DRAFT_DIR", tmp_path)
    kb.load_kb.cache_clear()
    try:
        block, _ = kb_draft.assemble("insurance_x", "보험업", "INSX", ["651"], _raw(), [], IDS)
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
