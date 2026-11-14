"""사업보고서 원문 파싱 — 섹션 분리, 표 파싱(병합 셀), 핵심 문장·매출 비중 표 추출."""

from scanner import report_parse as rp

RAW = """<P>1. 사업의 개요</P><P>당사는 철강 제품을 생산·판매하고 있습니다. 2025년 조강 생산량은 3,500만톤입니다.</P>
<P>2. 주요 제품 및 서비스</P>
<TABLE><TR><TD>(단위 : 백만원)</TD></TR></TABLE>
<TABLE>
<TR><TD ROWSPAN="2">사업부문</TD><TD ROWSPAN="2">구분</TD><TD COLSPAN="2">제58기</TD></TR>
<TR><TD>금 액</TD><TD>비 율(%)</TD></TR>
<TR><TD ROWSPAN="2">철강</TD><TD>국내</TD><TD>1,000</TD><TD>60.0</TD></TR>
<TR><TD>해외</TD><TD>500</TD><TD>30.0</TD></TR>
<TR><TD>기타</TD><TD>-</TD><TD>100</TD><TD>10.0</TD></TR>
<TR><TD>합 계</TD><TD>-</TD><TD>1,600</TD><TD>100.0</TD></TR>
</TABLE>
<P>3. 원재료 및 생산설비</P><P>주요 원재료는 철광석과 석탄입니다.</P>
<P>4. 매출 및 수주상황</P><P>당기 매출액은 1조 2,000억원입니다.EPC 수주가 늘었습니다.</P>"""


def test_sections_follow_standard_titles():
    secs = rp.parse_business(RAW)
    assert [(s["no"], s["key"]) for s in secs] == [(1, "overview"), (2, "product"), (3, "material"), (4, "sales")]
    assert "3,500만톤" in secs[0]["facts"][0]
    # 마침표 뒤 공백 없이 붙은 문장도 나뉜다
    assert any(x.startswith("EPC") for x in rp._sentences(secs[3]["text"]))


def test_rowspan_colspan_grid_and_unit():
    t = rp.parse_business(RAW)[1]["tables"][0]
    assert t["unit"] == "(단위 : 백만원)"
    assert t["rows"][0] == ["사업부문", "구분", "제58기", "제58기"]
    assert t["rows"][1] == ["사업부문", "구분", "금 액", "비 율(%)"]   # ROWSPAN 칸이 아래 행에 채워짐
    assert t["rows"][3] == ["철강", "해외", "500", "30.0"]


def test_share_table_excludes_total_and_keeps_labels():
    sh = rp.share_table(rp.parse_business(RAW))
    assert sh["period"] == "제58기"
    assert [(i["항목"], i["비중"]) for i in sh["items"]] == [("철강 · 국내", 60.0), ("철강 · 해외", 30.0), ("기타", 10.0)]


def test_plain_text_demo_falls_back_to_numbered_headings():
    secs = rp.parse_business("1. 사업의 개요\n당사는 건축 공사를 합니다.\n2. 매출 및 수익인식\n진행률로 수익을 인식합니다.")
    assert [s["title"] for s in secs] == ["사업의 개요", "매출 및 수익인식"]


def test_dart_title_structure_wins_over_inline_references():
    raw = ('<TITLE ATOC="Y">1. 사업의 개요</TITLE><P>당사는 은행업을 합니다. 자세한 내용은 4. 매출 및 수주상황 참고.</P>'
           '<TITLE ATOC="Y">2. 영업의 현황</TITLE><P>당기 순이자이익은 1조 2,000억원입니다.</P>'
           '<TITLE ATOC="Y">3. 파생상품거래 현황</TITLE><P>파생상품 거래가 있습니다.</P>')
    secs = rp.parse_business(raw)
    assert [(s["no"], s["title"], s["key"]) for s in secs] == [
        (1, "사업의 개요", "overview"), (2, "영업의 현황", "sales"), (3, "파생상품거래 현황", "risk")]


def test_plain_text_ignores_non_increasing_numbered_references():
    secs = rp.parse_business("1. 사업의 개요\n당사는 유통업을 합니다.\n2. 주요 제품 및 서비스\n상품을 판매합니다.\n"
                             "1. 사업의 개요\n(위 참조)\n3. 원재료 및 생산설비\n원재료는 없습니다.")
    assert [s["no"] for s in secs] == [1, 2, 3]
