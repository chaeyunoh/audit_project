"""최근 공시(OpenDART list.json) — 제목으로 주제를 붙이고, 감사에서 왜 보는지 한 줄을 단다.

공시 목록은 공개정보이며, 판단을 만들지 않는다: 제목 키워드로 '어느 주제의 공시인지'만 분류한다.
"""
from __future__ import annotations

import re

# (주제, 제목 키워드, 감사에서 볼 점) — 위에서부터 먼저 맞는 주제 하나
TOPICS: list[tuple[str, list[str], str]] = [
    ("소송·제재·사고", ["소송", "횡령", "배임", "제재", "과징금", "벌금", "불성실공시", "회생", "파산", "거래정지",
                   "상장적격성", "중대재해", "영업정지", "조회공시", "풍문", "해명"],
     "충당부채·우발부채 주석(기업회계기준서 1037), 법률 확인서, 부정위험, 손상 징후"),
    ("자금조달·자본", ["유상증자", "무상증자", "주식소각", "감자", "주식매수선택권", "전환사채", "신주인수권", "교환사채", "사채권", "증권신고서", "투자설명서",
               "자금차입", "단기차입", "채무보증", "담보제공"],
     "금융부채·자본 분류와 전환권 평가(1032·1109), 주식기준보상(1102), 약정 위반, 보증·담보 주석"),
    ("합병·분할·투자", ["합병", "분할", "타법인주식", "출자증권", "양수", "양도", "영업양", "자산양수", "주식교환", "공개매수"],
     "사업결합 회계(1103)·영업권, 처분손익, 연결범위 변경"),
    ("계약·수주", ["단일판매", "공급계약", "수주", "판매ㆍ공급", "계약체결", "계약해지"],
     "수익인식 시점·계약자산, 계약 해지에 따른 손실, 수주잔고와 공시 대사"),
    ("지배구조·주주", ["최대주주", "대량보유", "임원ㆍ주요주주", "임원·주요주주", "자기주식", "소유상황", "대표이사", "주주총회",
                  "특수관계인", "지배구조"],
     "특수관계자 식별·거래(감사기준서 550), 경영진 교체에 따른 통제 변화"),
    ("실적·배당", ["매출액또는손익", "손익구조", "영업(잠정)실적", "잠정실적", "현금ㆍ현물배당", "배당", "실적"],
     "잠정실적과 감사 후 수치의 차이, 배당가능이익"),
    ("정기·감사보고", ["사업보고서", "반기보고서", "분기보고서", "감사보고서", "내부회계", "감사인"],
     "전기 감사의견·핵심감사사항, 내부회계관리제도 지적사항"),
]
OTHER = ("기타", "")
TOPIC_NOTE = {t: note for t, _, note in TOPICS} | {OTHER[0]: OTHER[1]}
TOPIC_ORDER = [t for t, _, _ in TOPICS] + [OTHER[0]]
ROUTINE = {"정기·감사보고", "기타"}   # 첫 화면 카드에서는 뒤로 미룬다
# 자주 반복되는 신고(임원 지분 변동·IR 안내 등)는 목록·그래프에는 남기되 첫 화면 카드에서는 뺀다
_REPEAT = re.compile(r"소유상황보고서|대량보유상황보고서|안내공시|기업설명회|공시예고|대규모기업집단현황")


def is_repetitive(title: str) -> bool:
    return bool(_REPEAT.search(title.replace(" ", "")))


def topic_of(report_nm: str) -> str:
    flat = re.sub(r"\s+", "", report_nm)
    for name, kws, _ in TOPICS:
        if any(k.replace(" ", "") in flat for k in kws):
            return name
    return OTHER[0]


def is_correction(report_nm: str) -> bool:
    return bool(re.search(r"\[[^\]]*정정\]", report_nm))


def viewer_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def normalize(rows: list[dict]) -> list[dict]:
    """list.json 행 → 화면용 행 (최신순). rm '정' = 이후 정정 있음, '철' = 철회."""
    out = []
    for x in rows:
        nm = re.sub(r"\s+", " ", x.get("report_nm", "")).strip()
        d = x.get("rcept_dt", "")
        rm = x.get("rm", "") or ""
        out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d, "title": nm, "topic": topic_of(nm),
                    "filer": x.get("flr_nm", ""), "correction": is_correction(nm),
                    "later_corrected": "정" in rm, "withdrawn": "철" in rm,
                    "rcept_no": x.get("rcept_no", ""), "url": viewer_url(x.get("rcept_no", ""))})
    return sorted(out, key=lambda r: (r["date"], r["rcept_no"]), reverse=True)


def highlights(rows: list[dict], n: int = 4) -> list[dict]:
    """첫 화면 카드: 정기보고·기타가 아닌 공시를 최신순으로, 모자라면 나머지로 채운다."""
    def pick(cands: list[dict], out: list[dict]):
        for r in cands:   # 같은 제목은 한 번만
            if len(out) < n and r["title"] not in {x["title"] for x in out}:
                out.append(r)
    live = [r for r in rows if not r["withdrawn"]]
    out: list[dict] = []
    pick([r for r in live if r["topic"] not in ROUTINE and not is_repetitive(r["title"])], out)
    pick([r for r in live if not is_repetitive(r["title"])], out)
    pick(live, out)
    return out
