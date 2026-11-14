"""산업 카탈로그 — 지식베이스 구조 규칙(요약·가치사슬·그림·용어집)과 본부 지도 연결을 검사한다.
새 산업을 추가할 때 이 테스트가 형식 오류를 잡아 준다."""

from scanner import catalog, kb


def test_profile_is_complete_for_every_industry():
    for key, ind in kb.industries().items():
        p = catalog.profile(key)
        assert p["summary"], f"{key}: 산업 한 줄 요약(summary) 누락"
        assert p["traits"] and p["risks"] and p["top_risks"]
        assert len(p["risks"]) == sum(len(t["risks"]) for t in ind["traits"])
        assert all(a in catalog.assertions() for a in p["assertions"]), f"{key}: 용어집에 없는 경영진 주장"


def test_metric_rows_describe_formula_and_threshold():
    rows = catalog.metric_rows("construction")
    by = {r["지표"]: r for r in rows}
    assert by["매출원가율"]["산식"] == "매출원가 ÷ 매출 × 100"
    assert by["매출원가율"]["확인 신호 기준"] == "전년 대비 ±3%p 이상 변동"
    assert by["매출채권 회전일수"]["확인 신호 기준"] == "전년 대비 +15일 이상 변동"


def test_assertion_matrix_has_every_industry_assertion_cell():
    keys = list(kb.industries())
    rows = catalog.assertion_matrix(keys)
    assert len(rows) == len(keys) * len(catalog.assertions())
    con = {r["경영진 주장"]: r["검토 영역 수"] for r in rows if r["산업"] == "건설업"}
    assert con["평가와배분"] == 3 and con["완전성"] == 3


def test_shared_references_sorted_by_breadth():
    rows = catalog.shared_references(list(kb.industries()))
    assert rows[0]["산업 수"] == max(r["산업 수"] for r in rows)
    k1115 = next(r for r in rows if r["기준"] == "K-IFRS 제1115호")
    # 수익인식 기준서는 지식베이스의 모든 산업에 걸친다 (산업을 추가해도 깨지지 않도록 지식베이스에서 계산)
    uses = [k for k in kb.industries()
            if any("K-IFRS 제1115호" in r["references"] for t in kb.traits(k) for r in t["risks"])]
    assert k1115["산업 수"] == len(uses) == len(kb.industries())


def test_stage_info_covers_value_chain_with_known_icons():
    import illustrations
    for key in kb.industries():
        p = catalog.profile(key)
        assert set(p["stage_info"]) == set(p["value_chain"]), f"{key}: 단계 설명이 가치사슬과 다름"
        for stage, d in p["stage_info"].items():
            assert d["icon"] in illustrations.icon_keys(), f"{key}/{stage}: 없는 일러스트 '{d['icon']}'"
            assert d["do"] and d["money"] and d["books"]


def test_sector_map_points_only_to_known_industries_and_risks():
    base = {r["risk_id"] for r in kb.baseline_risks()}
    for s in catalog.systems():
        for d in s["divisions"]:
            if d.get("kind") == "function":
                assert d.get("focus") and set(d["focus"]) <= base, d["code"]
            else:
                assert d["sectors"], d["code"]
                for sec in d["sectors"]:
                    assert sec.get("kb") in (None, *kb.industries()), sec
    # 지식베이스의 모든 산업은 적어도 한 본부 체계에 속한다 (한영 체계에는 금융 본부가 없음)
    for key in kb.industries():
        if kb.is_draft_file(key):   # 초안 생성기로 추가된 산업은 검토 후 본부 지도에 넣는다
            continue
        assert catalog.divisions_of(key), key


def test_svg_has_no_script_and_escapes_label():
    import illustrations
    out = illustrations.svg("build", label='<x>"')
    assert "<script" not in out and "viewBox" in out
    assert "<x>" not in out and "&lt;x&gt;&quot;" in out


def test_generic_chains_cover_ksic_and_use_known_icons():
    import illustrations
    for c in kb.generic_chains():
        assert set(c["stage_info"]) == set(c["value_chain"]), c["key"]
        for d in c["stage_info"].values():
            assert d["icon"] in illustrations.icon_keys() and d["keywords"], c["key"]
    assert kb.generic_chain("1811")["key"] == "manufacturing"      # 인쇄업 → 제조업 일반형
    assert kb.generic_chain("49301")["key"] == "transport"
    assert kb.generic_chain("85")["key"] == "services"              # 대분류 밖 → 서비스업 일반형
    assert kb.generic_chain("") is None
    p = catalog.profile(kb.unsupported_key("1811"))
    assert p["value_chain"] and p["traits"] == [] and p["risks"] == []   # 가치사슬만, 판단(특성·위험)은 없음


def test_every_industry_has_group_and_industry_icon():
    import illustrations
    for key, ind in kb.industries().items():
        assert ind.get("group"), key
        assert "<circle cx=\"32\" cy=\"32\" r=\"22\"" not in illustrations.industry_svg(key), f"{key}: 산업 일러스트 없음"
