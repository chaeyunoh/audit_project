"""최근 공시 — 제목 주제 분류, 정정 표시, 첫 화면 카드 선택 (네트워크 없이)."""
from scanner import disclosures as ds


def _row(d, nm, rm="", no=None):
    return {"rcept_dt": d, "report_nm": nm, "rm": rm, "flr_nm": "회사", "rcept_no": no or f"{d}000001"}


def test_topic_of_titles():
    assert ds.topic_of("소송등의제기ㆍ신청(일정금액 이상의 청구)") == "소송·제재·사고"
    assert ds.topic_of("중대재해발생(종속회사의주요경영사항)") == "소송·제재·사고"
    assert ds.topic_of("주요사항보고서(전환사채권발행결정)") == "자금조달·자본"
    assert ds.topic_of("[기재정정]단일판매ㆍ공급계약체결") == "계약·수주"
    assert ds.topic_of("회사합병결정") == "합병·분할·투자"
    assert ds.topic_of("임원ㆍ주요주주특정증권등소유상황보고서") == "지배구조·주주"
    assert ds.topic_of("연결재무제표기준영업(잠정)실적(공정공시)") == "실적·배당"
    assert ds.topic_of("기업설명회(IR)개최(안내공시)") == "기타"


def test_normalize_sorts_latest_first_and_flags():
    rows = ds.normalize([_row("20260101", "회사합병결정"), _row("20261101", "[기재정정]단일판매ㆍ공급계약체결", "정")])
    assert rows[0]["date"] == "2026-11-01" and rows[0]["correction"] and rows[0]["later_corrected"]
    assert rows[0]["url"].endswith("rcpNo=20261101000001")


def test_highlights_skip_repetitive_and_duplicate_titles():
    rows = ds.normalize([
        _row("20261110", "임원ㆍ주요주주특정증권등소유상황보고서", no="1"),
        _row("20261109", "임원ㆍ주요주주특정증권등소유상황보고서", no="2"),
        _row("20261108", "타인에대한채무보증결정", no="3"),
        _row("20261107", "타인에대한채무보증결정", no="4"),
        _row("20261106", "분기보고서 (2026.09)", no="5"),
        _row("20261105", "중대재해발생", "철", no="6"),
    ])
    titles = [x["title"] for x in ds.highlights(rows, 3)]
    assert titles[0] == "타인에대한채무보증결정" and titles.count("타인에대한채무보증결정") == 1
    assert "중대재해발생" not in titles                     # 철회된 공시는 빼고
    assert titles[1] == "분기보고서 (2026.09)"              # 반복 신고보다 정기보고가 먼저
    assert ds.TOPIC_NOTE["소송·제재·사고"]
