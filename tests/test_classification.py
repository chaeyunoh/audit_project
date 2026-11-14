"""산업 판별·기업 후보 — 공식 업종코드(KSIC)가 근거이고, 지식베이스에 없는 업종을 억지로 끼워 넣지 않는다."""
from scanner import catalog, kb, ksic
from scanner.collect import rank_corps
from scanner.models import SourceDoc
from scanner.pipeline import resolve_industry

DOC = [SourceDoc(doc_id="S01", title="t", publisher="p",
                 raw_text="공사 수주 도급 시공 건설 분양 공사 공사 공사 공사 매장 가맹")]


def test_ksic_in_kb_maps_to_kb_industry():
    assert resolve_industry({"induty_code": "41221"}, DOC) == "construction"   # 현대건설
    assert resolve_industry({"induty_code": "2612"}, DOC) == "semiconductor"   # SK하이닉스
    assert resolve_industry({"induty_code": "47122"}, DOC) == "franchise_retail"  # 편의점


def test_ksic_outside_kb_is_not_forced_into_kb_even_if_text_matches():
    # 본문에 건설 키워드가 많아도, 업종코드가 인쇄업이면 건설업으로 분류하지 않는다
    key = resolve_industry({"induty_code": "18111"}, DOC)
    assert key == "ksic:18111" and not kb.is_supported(key)
    assert kb.industry(key)["name"] == ksic.division_name("18111") and kb.traits(key) == []


def test_new_industries_map_by_ksic():
    assert resolve_industry({"induty_code": "24111"}, DOC) == "steel"          # POSCO 계열
    assert resolve_industry({"induty_code": "30121"}, DOC) == "automobile"
    assert resolve_industry({"induty_code": "63120"}, DOC) == "platform"       # 카카오·네이버
    assert resolve_industry({"induty_code": "64121"}, DOC) == "banking"        # 기업은행
    assert resolve_industry({"induty_code": "264"}, DOC) == "ksic:264"         # 삼성전자 업종은 그대로 미지원


def test_car_rental_is_not_franchise():
    assert kb.industry_from_ksic("76110") is None


def test_text_fallback_only_without_code_and_needs_enough_evidence():
    assert resolve_industry({}, DOC) == "construction"
    weak = [SourceDoc(doc_id="S01", title="t", publisher="p", raw_text="공사 일정")]
    try:
        resolve_industry({}, weak)
        assert False, "근거가 약하면 산업을 정하지 않아야 함"
    except ValueError:
        pass


def test_related_industry_by_same_division():
    assert kb.related_industry("264") == "semiconductor"   # 삼성전자(통신장비) → 같은 26 중분류
    assert kb.related_industry("18111") is None


def test_ksic_label():
    assert ksic.label("63120") == "KSIC 63120 · 정보서비스업"
    assert ksic.label("") == "업종코드 없음"


def test_sectors_for_ksic_per_system():
    hits = {(x["체계"], x["본부"], x["섹터"]) for x in catalog.sectors_for_ksic("2411")}
    assert ("IM·CM·IGH·ICE·B&F 체계", "IM", "철강") in hits
    assert ("한영 본부 체계", "1본부", "산업재·건설") in hits
    bank = catalog.sectors_for_ksic("64992")
    assert [x["본부"] for x in bank if x["체계"].startswith("IM")] == ["B&F"]


def test_rank_corps_prefers_listed_over_unlisted_same_name():
    corps = [{"corp_code": "1", "corp_name": "삼성", "stock_code": ""},
             {"corp_code": "2", "corp_name": "삼성전자", "stock_code": "005930"},
             {"corp_code": "3", "corp_name": "삼성물산", "stock_code": "028260"},
             {"corp_code": "4", "corp_name": "포스코", "stock_code": ""},
             {"corp_code": "5", "corp_name": "POSCO홀딩스", "stock_code": "005490"},
             {"corp_code": "6", "corp_name": "(주)카카오", "stock_code": "035720"}]
    assert [c["corp_code"] for c in rank_corps(corps, "삼성")] == ["2", "3"]   # 비상장 '삼성'은 후보에서 제외
    assert [c["corp_code"] for c in rank_corps(corps, "삼성", listed_only=False)][-1] == "1"
    assert rank_corps(corps[:1], "삼성") == []                                    # 비상장만 있으면 후보 없음
    assert rank_corps(corps, "카카오")[0]["corp_code"] == "6"                      # (주) 표기 무시
    assert rank_corps(corps, "posco")[0]["corp_code"] == "5"                       # 대소문자 무시
    assert rank_corps(corps, "  ") == []


def test_alias_brings_registered_name_first():
    corps = [{"corp_code": "4", "corp_name": "포스코엠텍", "stock_code": "009520"},
             {"corp_code": "5", "corp_name": "POSCO홀딩스", "stock_code": "005490"}]
    assert rank_corps(corps, "포스코")[0]["corp_code"] == "5"


def test_business_section_uses_title_tags_not_inline_mentions():
    from scanner.collect import DartCollector
    doc = ("<P>자세한 사항은 'II. 사업의 내용'을 참고. 'III. 재무에 관한 사항' 참조</P>"
           '<TITLE ATOC="Y">II. 사업의 내용</TITLE><P>진짜 본문</P>'
           '<TITLE ATOC="Y">III. 재무에 관한 사항</TITLE>')
    assert DartCollector.business_section(doc).strip() == "<P>진짜 본문</P>"


def test_stale_listed_company_ranks_below_active_one():
    from datetime import date
    old, new = "20150101", f"{date.today().year}0101"
    corps = [{"corp_code": "1", "corp_name": "삼성수산", "stock_code": "052560", "modify_date": old},
             {"corp_code": "2", "corp_name": "삼성전자", "stock_code": "005930", "modify_date": new}]
    assert [c["corp_code"] for c in rank_corps(corps, "삼성")] == ["2", "1"]


def test_is_listed_uses_corp_cls():
    from scanner.collect import is_listed
    assert is_listed({"corp_cls": "Y"}) and is_listed({"corp_cls": "K"}) and is_listed({"corp_cls": "N"})
    assert not is_listed({"corp_cls": "E"}) and not is_listed({})


def test_missing_credentials_become_analyzer_error():
    from scanner.analyze import AnalyzerError, ClaudeAnalyzer
    a = ClaudeAnalyzer.__new__(ClaudeAnalyzer)   # 네트워크·키 없이 _call의 예외 변환만 확인
    import anthropic
    a.anthropic, a.model, a.effort = anthropic, "m", "low"

    class _NoAuth:
        class beta:
            class messages:
                @staticmethod
                def create(**_):
                    raise TypeError('"Could not resolve authentication method. Expected one of api_key"')
    a.client = _NoAuth
    try:
        a._call("x", {})
        assert False
    except AnalyzerError as e:
        assert "ANTHROPIC_API_KEY" in str(e)


def test_holding_company_code_needs_business_text():
    bank_text = "대출채권 예수부채 순이자마진 기대신용손실 고정이하여신 " * 8
    bank = [SourceDoc(doc_id="S02", title="t", publisher="p", raw_text=bank_text)]
    assert resolve_industry({"induty_code": "64992"}, bank) == "banking"       # 신한지주·KB금융
    key = resolve_industry({"induty_code": "64992"}, DOC)                    # SK처럼 근거가 약하면
    assert key == "ksic:64992" and kb.industry(key)["template"] == "지주회사 일반형"


def test_ksic_prefixes_match_real_companies():
    """실제 상장사 업종코드(OpenDART 기업개황)로 확인한 분류. 넓은 접두어가 다른 업종을 끌어오지 않게 한다."""
    expect = {
        # 석유화학·정유 (맞게 들어와야 함)
        "20111": "chemical",   # 롯데케미칼, LG화학
        "201": "chemical",     # 금호석유화학
        "2050": "chemical",    # 효성티앤씨 (화학섬유)
        "19210": "chemical",   # S-Oil
        # 화장품은 석유화학이 아님 (에이피알·아모레퍼시픽·코스맥스 20423, LG생활건강 20422)
        "20423": None, "20422": None,
        # 철강
        "2411": "steel", "241": "steel",
        # 비철금속 제련은 철강이 아님 (고려아연 24213, 풍산 242)
        "24213": None, "242": None,
    }
    for code, key in expect.items():
        assert kb.industry_from_ksic(code) == key, (code, kb.industry_from_ksic(code))


def test_subclass_names_avoid_misleading_division_names():
    assert ksic.label("20423") == "KSIC 20423 · 화장품 제조업"          # 에이피알·아모레퍼시픽
    assert ksic.label("24213") == "KSIC 24213 · 비철금속 제련업"        # 고려아연
    assert ksic.label("63120") == "KSIC 63120 · 정보서비스업"          # 세부 이름이 없으면 중분류
