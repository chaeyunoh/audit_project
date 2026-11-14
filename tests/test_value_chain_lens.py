"""가치사슬 × 사업보고서 연결 — 단계 키워드, 본문+표 검색, 원문 강조(이스케이프)."""
from scanner import catalog, kb
from scanner.report_parse import find_sentences, keyword_counts, stage_keywords

SECS = [
    {"no": 1, "key": "overview", "title": "사업의 개요", "tables": [],
     "text": "당사는 기술형 입찰 중심으로 수주를 확대하고 있습니다. 준공 이후 하자보수 충당부채를 설정합니다."},
    {"no": 4, "key": "sales", "title": "매출 및 수주상황", "text": "",
     "tables": [{"unit": "", "rows": [["구분", "수주잔고"], ["국내 수주 공사", "1,000억원"]]}]},
]


def test_stage_keywords_include_stage_names_and_trait_keywords():
    p = catalog.profile("construction")
    kws = stage_keywords(p["traits"], p["value_chain"])
    assert set(p["value_chain"]) <= set(kws)
    assert "착공" in kws["착공"]                       # 특성이 없는 단계도 이름으로 찾는다
    assert "수주" in kws["수주·입찰"] and "입찰" in kws["수주·입찰"]
    trait = next(t for t in p["traits"] if t["stage"] == "도급계약")
    assert set(trait["detect_keywords"]) <= set(kws["도급계약"])


def test_counts_and_sentences_cover_body_and_tables():
    c = keyword_counts(SECS, ["수주", "입찰", "없는말"])
    assert c["수주"] == 2 and c["입찰"] == 1 and c["없는말"] == 0   # 본문 1 + 표 본문 행 1 (머리 행은 제외)
    found = find_sentences(SECS, ["수주", "입찰"], limit=5)
    assert found[0]["hits"] == ["수주", "입찰"]                      # 키워드를 많이 담은 문장 먼저
    assert any(x["section"] == "매출 및 수주상황" for x in found)      # 표 행도 원문으로 나온다
    assert len({x["sentence"] for x in found}) == len(found)


def test_highlight_escapes_before_marking():
    import industry_lens
    out = industry_lens.highlight("<b>수주</b> & 입찰", ["수주"])
    assert "<b>" not in out and "&lt;b&gt;<mark>수주</mark>&lt;/b&gt;" in out and "&amp;" in out


def test_no_division_badges_in_classification():
    import snapshot_view
    assert "본부" not in snapshot_view.classification_badges("2411", kb.industry_from_ksic("2411"))
