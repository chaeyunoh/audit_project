"""핵심감사사항(KAM) 수집·파싱.

KAM은 감사인이 그 회사 감사에서 '가장 유의적'이라고 판단한 사항과 대응 절차를 직접 적은 공개 자료다.
같은 산업 회사 몇 곳의 KAM을 모으면, 그 산업에서 감사인이 실제로 무엇을 중요하게 보는지가 드러난다
→ 산업 지식베이스 초안의 가장 좋은 근거.

두 출처를 함께 쓴다.
  1) OpenDART '회계감사인의 명칭 및 감사의견' API의 core_adt_matter: KAM 제목 (짧고 확실함)
  2) 사업보고서 원문 안의 감사보고서: 제목 · 결정 이유 · 감사 절차 (본문을 파싱)
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .clean import strip_markup

_START = re.compile(r"핵심감사사항\s*핵심감사사항은\s*우리의")
_END = re.compile(r"재무제표에\s*대한\s*경영진과\s*지배기구의\s*책임")
_WHY = "핵심감사사항으로 결정한 이유"
_HOW = re.compile(r"핵심감사사항이\s*감사에서\s*다루어진\s*방법")


class KAM(BaseModel):
    title: str
    why: str = ""
    procedures: list[str] = Field(default_factory=list)
    company: str = ""
    auditor: str = ""
    year: str = ""


def norm_title(t: str) -> str:
    return re.sub(r"[\s·,()\[\]0-9.]", "", t)


def titles_from_api(rows: list[dict]) -> tuple[list[str], str]:
    """core_adt_matter → ['건설중인자산의 …', …], 감사인. 당기 행만 쓴다 ('(당기)' 표기)."""
    cur = [r for r in rows if "당기" in (r.get("bsns_year") or "")] or rows[:1]
    out: list[str] = []
    for r in cur:
        for t in split_titles(r.get("core_adt_matter") or ""):
            if t not in ("-", "해당사항 없음") and norm_title(t) not in {norm_title(x) for x in out}:
                out.append(t)
    return out, (cur[0].get("adtor") or "") if cur else ""


# 줄 끝이 이 글자면 제목이 다음 줄로 이어진 것 (예: '…산출 시 적용된' + '손해율 가정')
_CONTINUES = ("된", "한", "인", "는", "의", "및", "중", "에", "과", "와", "로", "을", "를", "시", "등")


def split_titles(text: str) -> list[str]:
    """API의 KAM 제목 칸 → 제목 목록. 긴 제목은 줄이 바뀌어 들어오므로
    번호('1)', '2.')가 있으면 번호로 나누고, 없으면 '이어지는 줄'을 합친다."""
    text = text.strip()
    if not text:
        return []
    if re.search(r"(?:^|\n)\s*\d+\s*[.)]", text):
        parts = re.split(r"(?:^|\n)\s*\d+\s*[.)]\s*", text)
        return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    titles: list[str] = []
    for line in (x.strip() for x in text.splitlines() if x.strip()):
        if titles and titles[-1].endswith(_CONTINUES):
            titles[-1] += " " + line
        else:
            titles.append(line)
    return titles


_BULLET = re.compile(r"(?:^|\n|\s|(?<=[가-힣)]))[-ㆍ•·]\s*(?=[가-힣A-Za-z(])")
_INTRO = re.compile(r"[^.\n]*(?:다음을\s*포함한\s*감사절차|주요\s*감사절차는\s*다음과\s*같|감사절차를\s*수행하였습니다)[^.\n]*\.?")


def _split_procedures(text: str) -> list[str]:
    """회계법인마다 글머리표가 다르다: '- 절차'(삼정), '-절차'(삼일), 'ㆍ 절차'(안진), 줄바꿈 없이 붙은 '평가- 다음'."""
    text = _INTRO.sub("\n", text)
    parts = _BULLET.split(text)
    return [re.sub(r"\s+", " ", p).strip(" .") for p in parts if len(p.strip()) >= 8]


def parse_filing(raw: str) -> list[KAM]:
    """사업보고서 원문(연결·별도 감사보고서 포함)에서 KAM을 파싱. 같은 제목은 한 번만."""
    plain = strip_markup(raw)
    found: dict[str, KAM] = {}
    for m in _START.finditer(plain):
        end = _END.search(plain, m.end())
        block = plain[m.end(): end.start() if end else m.end() + 20000]
        pieces = block.split(_WHY)
        # pieces[0]의 마지막 줄 = 첫 KAM 제목, 이후 각 조각 = (이유+절차) … 다음 KAM 제목
        title = pieces[0].strip().splitlines()[-1].strip() if pieces[0].strip() else ""
        for i, body in enumerate(pieces[1:], start=1):
            how = _HOW.search(body)
            why = body[:how.start()] if how else body
            rest = body[how.end():] if how else ""
            lines = rest.strip().splitlines()
            # 마지막 조각이 아니면, 절차 문단의 마지막 줄이 다음 KAM 제목이다
            has_next = i < len(pieces) - 1
            next_title = lines[-1].strip() if has_next and lines else ""
            proc_text = "\n".join(lines[:-1] if next_title else lines)
            proc_text = re.sub(r"^.*?주요\s*감사절차는\s*다음과\s*같습니다\.?", "", proc_text, flags=re.S)
            if title and norm_title(title) not in found:
                found[norm_title(title)] = KAM(title=title, why=re.sub(r"\s+", " ", why).strip()[:1200],
                                               procedures=_split_procedures(proc_text)[:10])
            title = next_title
    return list(found.values())


def merge(api_titles: list[str], parsed: list[KAM]) -> list[KAM]:
    """API 제목을 기준으로, 본문에서 파싱한 이유·절차를 붙인다. 본문에서 못 찾은 제목도 제목만으로 남긴다."""
    by = {norm_title(k.title): k for k in parsed}
    out = []
    for t in api_titles or [k.title for k in parsed]:
        k = by.get(norm_title(t)) or next((v for n, v in by.items() if norm_title(t) in n or n in norm_title(t)), None)
        out.append(k.model_copy(update={"title": t}) if k else KAM(title=t))
    return out
