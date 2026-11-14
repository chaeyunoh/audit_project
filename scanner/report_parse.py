"""사업보고서 'II. 사업의 내용' 구조화 — 표준 소제목(1~7)으로 나누고, 표·핵심 수치를 뽑는다.

결정적 파싱만 한다 (AI 없음). 원문 문장을 그대로 쓰며 요약문을 지어내지 않는다.
DART 원문(XML 마크업)과 데모용 평문 모두 처리한다.
"""
from __future__ import annotations

import html
import re

from .clean import strip_markup

# 2019년 이후 사업보고서 작성기준의 '사업의 내용' 표준 소제목
STANDARD = [
    ("사업의 개요", r"사업의\s*개요", "overview"),
    ("주요 제품 및 서비스", r"주요\s*제품\s*(?:및|등)\s*서비스", "product"),
    ("원재료 및 생산설비", r"원재료\s*및\s*생산\s*설비", "material"),
    ("매출 및 수주상황", r"매출\s*및\s*수주\s*상황", "sales"),
    ("위험관리 및 파생거래", r"위험\s*관리\s*및\s*파생\s*(?:상품\s*)?거래", "risk"),
    ("주요계약 및 연구개발활동", r"주요\s*계약\s*및\s*연구\s*개발\s*활동", "rnd"),
    ("기타 참고사항", r"기타\s*참고\s*사항", "etc"),
]
_STD = re.compile(r"(?:^|>|\n)\s*([1-9])\s*\.\s*(" + "|".join(f"(?:{p})" for _, p, _ in STANDARD) + r")", re.I)
_GENERIC = re.compile(r"(?:^|>|\n)\s*([1-9])\s*\.\s*([가-힣][^<\n.]{1,24})(?=\s*(?:<|\n))")
_TABLE = re.compile(r"<TABLE\b.*?</TABLE>", re.S | re.I)
_ROW = re.compile(r"<TR\b.*?</TR>", re.S | re.I)
_CELL = re.compile(r"<(TD|TH|TE|TU)\b([^>]*)>(.*?)</\1>", re.S | re.I)
# 숫자 + 단위 (예: 25조 5,151억원, 3,500만톤, 69,402,839백만원, 41.7%, 1,302건)
NUM_UNIT = re.compile(r"\d[\d,.]*\s*(?:조\s*\d[\d,]*\s*억\s*원|조\s*원|억\s*원|백만\s*원|천\s*원|만\s*원|원"
                      r"|억\s*달러|만\s*달러|달러|만\s*톤|천\s*톤|톤|만\s*대|대|만\s*명|명|%|MW|GW|GWh"
                      r"|개사|개국|개점|개소|건)")
_NUM_FACT = NUM_UNIT
MAX_TABLES, MAX_ROWS, MAX_CELL = 12, 40, 80


def _clean_cell(x: str) -> str:
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
    return t[:MAX_CELL]


def _advance(carry: dict, col: int) -> int:
    """ROWSPAN 칸 하나를 이번 행에서 썼다: 남은 행 수를 줄이고 다음 열로."""
    carry[col][0] -= 1
    if carry[col][0] <= 0:
        del carry[col]
    return col + 1


def parse_tables(raw: str) -> list[dict]:
    """표 → {'unit', 'rows'}. '(단위 : 백만원)'만 있는 한 칸짜리 표는 다음 표의 단위로 붙인다."""
    out, unit = [], ""
    for t in _TABLE.findall(raw):
        rows, carry = [], {}  # carry: 열 → (남은 행 수, 값)  — ROWSPAN으로 아래 행까지 이어지는 칸
        for r in _ROW.findall(t)[:MAX_ROWS]:
            cells, col = [], 0
            for _, attrs, body in _CELL.findall(r):
                while col in carry:  # 위에서 내려온 칸을 먼저 채운다
                    cells.append(carry[col][1])
                    col = _advance(carry, col)
                cspan = re.search(r"COLSPAN=\"?(\d+)", attrs, re.I)
                rspan = re.search(r"ROWSPAN=\"?(\d+)", attrs, re.I)
                val = _clean_cell(body)
                for _ in range(min(int(cspan.group(1)) if cspan else 1, 12)):
                    if rspan and int(rspan.group(1)) > 1:
                        carry[col] = [int(rspan.group(1)) - 1, val]
                        col += 1
                    else:
                        col += 1
                    cells.append(val)
            while col in carry:
                cells.append(carry[col][1])
                col = _advance(carry, col)
            # 이번 행에서 새로 생긴 carry는 다음 행부터 쓰이므로 그대로 두고, 이미 쓰인 것은 _advance가 줄였다
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        if len(rows) == 1 and len(rows[0]) <= 2 and "단위" in " ".join(rows[0]):
            unit = " ".join(c for c in rows[0] if c)
            continue
        width = max(len(r) for r in rows)
        out.append({"unit": unit, "rows": [r + [""] * (width - len(r)) for r in rows]})
        unit = ""
        if len(out) >= MAX_TABLES:
            break
    return out


def _sentences(text: str) -> list[str]:
    # '…니다.EPC'처럼 마침표 뒤 공백 없이 붙은 문장도 나눈다 (숫자 소수점 '3.4'는 건드리지 않음)
    parts = re.split(r"(?<=[다요음함됨임])\.\s*(?=\S)|(?<=[.?!])\s+|\n", text)
    return [p.strip() for p in parts if 12 <= len(p.strip()) <= 260]


def key_facts(text: str, limit: int = 5) -> list[str]:
    """숫자+단위가 들어간 원문 문장 (수주잔고, 점유율, 생산능력 등)."""
    out = []
    for s in _sentences(text):
        if _NUM_FACT.search(s) and not re.match(r"^[\d\s,.%()\-|]+$", s) and s not in out:
            out.append(s)
            if len(out) >= limit:
                break
    return out


def lead(text: str, n: int = 2) -> list[str]:
    """섹션 첫머리의 설명 문장 (표 제목·단위 줄은 건너뜀)."""
    return [s for s in _sentences(text) if "단위" not in s and not re.match(r"^[가-하\d][.)]\s*\S{0,20}$", s)][:n]


# 금융업 등 다른 작성기준의 소제목도 같은 아이콘·분류로 묶는다
_KEY_HINTS = [("overview", r"사업의\s*개요"), ("product", r"주요\s*제품"), ("sales", r"매출|수주|영업의\s*현황"),
              ("material", r"원재료|생산\s*설비|영업\s*설비"), ("risk", r"위험\s*관리|파생"),
              ("rnd", r"연구\s*개발|주요\s*계약"), ("etc", r"기타|참고\s*사항|재무\s*건전성")]
_TITLE = re.compile(r"<TITLE\b[^>]*>(.*?)</TITLE>", re.S | re.I)


def _key_of(title: str) -> str:
    return next((k for k, p in _KEY_HINTS if re.search(p, title)), "etc")


def _section(no: int, title: str, seg: str) -> dict:
    text = strip_markup(_TABLE.sub("\n", seg))
    return {"no": no, "title": title, "key": _key_of(title), "text": text,
            "tables": parse_tables(seg), "facts": key_facts(text), "lead": lead(text)}


def parse_business(raw: str) -> list[dict]:
    """사업의 내용 → [{'no','title','key','text','tables','facts','lead'}].

    1) DART 원문: 문서 구조의 소제목(<TITLE>)으로 나눈다 — 본문 속 '4. 매출…' 같은 참조 문구에 속지 않는다.
    2) 평문(데모 등): 줄 머리의 '1. 제목' — 번호가 커지는 순서인 것만 소제목으로 인정한다.
    """
    titles = list(_TITLE.finditer(raw))
    if titles:
        out = []
        for i, m in enumerate(titles):
            seg = raw[m.end(): titles[i + 1].start() if i + 1 < len(titles) else len(raw)]
            t = re.sub(r"\s+", " ", strip_markup(m.group(1))).strip()
            num = re.match(r"^(\d{1,2})\s*\.\s*(.+)$", t)
            out.append(_section(int(num.group(1)) if num else i + 1, num.group(2) if num else t, seg))
        return [s for s in out if s["text"] or s["tables"]]

    hits = list(_STD.finditer(raw))
    if len(hits) < 2:
        hits = list(_GENERIC.finditer(raw))
    kept, last = [], 0
    for m in hits:  # 번호가 1,2,3… 커지는 것만 (본문 중 '4. 매출 참조' 같은 반복 제외)
        if int(m.group(1)) > last:
            kept.append(m)
            last = int(m.group(1))
    if not kept:
        return [_section(1, "사업의 내용", raw)] if strip_markup(raw) else []
    out = []
    for i, m in enumerate(kept):
        seg = raw[m.end(): kept[i + 1].start() if i + 1 < len(kept) else len(raw)]
        title_raw = re.sub(r"\s+", " ", m.group(2)).strip()
        title = next((t for t, p, _ in STANDARD if re.fullmatch(p, title_raw, re.I)), title_raw)
        out.append(_section(int(m.group(1)), title, seg))
    return out


def share_table(sections: list[dict]) -> dict | None:
    """'비중/비율' 열이 있는 표에서 (항목, 비중%) 목록을 찾는다 — 제품·부문 구성 차트용. 못 찾으면 None."""
    for sec in sections:
        if sec["key"] not in ("product", "sales", "overview"):
            continue
        for t in sec["tables"]:
            rows = t["rows"]
            if len(rows) < 3:
                continue
            for h in range(min(3, len(rows))):
                cols = [j for j, c in enumerate(rows[h]) if re.search(r"비중|비율|구성비|%", c.replace(" ", ""))]
                if not cols:
                    continue
                col, items = cols[0], []   # 첫 '비율' 열 = 보통 최근 사업연도
                for r in rows[h + 1:]:
                    # 항목명: 비율 열 앞의 글자 칸들 (긴 설명 칸은 빼고, 같은 값 반복은 한 번만)
                    parts = [c for c in dict.fromkeys(r[:col]) if c and len(c) <= 12
                             and not re.fullmatch(r"[△▲+\-()\s]*[\d,.]+%?\)?", c)   # 숫자 칸
                             and not re.fullmatch(r"[\-–—.\s]+", c)                    # '-' 같은 빈 표시
                             and not re.search(r"제\s*\d+\s*기", c)]
                    label = " · ".join(parts)
                    v = re.sub(r"[^\d.\-]", "", r[col]) if col < len(r) else ""
                    if label and v and re.fullmatch(r"-?\d+(\.\d+)?", v) and not re.search(r"합\s*계|^계$|소\s*계", label):
                        items.append({"항목": label, "비중": float(v)})
                labels = [i["항목"] for i in items]
                if (2 <= len(items) <= 25 and len(set(labels)) == len(labels)   # 같은 항목 반복 = 여러 표가 섞인 것
                        and 50 <= sum(i["비중"] for i in items) <= 205):
                    period = rows[h - 1][col] if h > 0 and re.search(r"\d", rows[h - 1][col]) else ""
                    return {"section": sec["title"], "header": rows[h][col], "period": period, "items": items}
    return None


# ---------------------------------------------------------------- 가치사슬 ↔ 사업보고서 연결
def _units(sec: dict) -> list[str]:
    """한 섹션의 검색 단위: 본문 문장 + 표의 행('칸 | 칸')."""
    rows = [" | ".join(c for c in dict.fromkeys(r) if c) for t in sec.get("tables", []) for r in t.get("rows", [])[1:]]
    return _sentences(sec.get("text", "")) + [r for r in rows if 8 <= len(r) <= 260]


def keyword_counts(sections: list[dict], keywords: list[str]) -> dict[str, int]:
    """사업의 내용(본문 + 표)에서 키워드별 등장 횟수 (공백 무시)."""
    text = re.sub(r"\s+", "", " ".join(u for s in sections for u in _units(s)))
    return {k: text.count(re.sub(r"\s+", "", k)) for k in dict.fromkeys(keywords) if k.strip()}


def find_sentences(sections: list[dict], keywords: list[str], limit: int = 5) -> list[dict]:
    """키워드가 들어간 원문 문장 → {'section','sentence','hits'}. 키워드를 많이 담은 문장 먼저, 같은 문장은 한 번."""
    kws = [k for k in dict.fromkeys(keywords) if k.strip()]
    found, seen = [], set()
    for sec in sections:
        for s in _units(sec):
            flat = re.sub(r"\s+", "", s)
            hits = [k for k in kws if re.sub(r"\s+", "", k) in flat]
            if hits and s not in seen:
                seen.add(s)
                found.append({"section": sec["title"], "sentence": s, "hits": hits})
    found.sort(key=lambda x: -len(x["hits"]))   # 안정 정렬: 같은 수면 보고서 순서
    return found[:limit]


def stage_keywords(traits: list[dict], stages: list[str] = (), stage_info: dict | None = None) -> dict[str, list[str]]:
    """가치사슬 단계별 검색어 = 단계 이름('·'로 나눈 각 낱말) + 단계 keywords(업종 일반형) + 그 단계 산업 특성의 detect_keywords."""
    out: dict[str, list[str]] = {st: [w.strip() for w in st.split("·") if len(w.strip()) >= 2]
                                 + list((stage_info or {}).get(st, {}).get("keywords", [])) for st in stages}
    for t in traits:
        out.setdefault(t.get("stage", ""), []).extend(t.get("detect_keywords", []))
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}
