"""시각 블록(HTML) 생성기 — 첫 화면, 쉬운 말 요약, 가치사슬 일러스트, 작동 원리.

원칙
  - 표준 위젯으로 안 되는 '보여주기' 블록만 HTML로 만든다. 클릭이 필요한 것은 Streamlit 버튼을 쓴다.
  - 지식베이스 문자열은 모두 html.escape 후 삽입한다. JavaScript는 쓰지 않는다.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

import illustrations as art

CSS = Path(__file__).resolve().parent / "assets" / "style.css"
STATUS_CLASS = {"FACT": "fact", "INFERENCE": "inf", "UNVERIFIED": "unv"}


def inject_css():
    st.html(CSS)


def _h(x) -> str:
    return escape(str(x))


def block(inner: str):
    st.html(f'<div class="ais">{inner}</div>')


def section(title: str, cap: str = ""):
    block(f'<div class="ais-sec"><div class="h2">{_h(title)}</div><div class="cap">{_h(cap)}</div></div>')


def plain(tag: str, text: str, sub: str = ""):
    block(f'<div class="ais-plain"><div class="tag">{_h(tag)}</div><div class="txt">{_h(text)}</div>'
          + (f'<div class="sub">{_h(sub)}</div>' if sub else "") + "</div>")


# ---------------------------------------------------------------- 첫 화면
def hero(title: str, lead: str, dash_title: str, dash_sub: str,
         cards: list[tuple[str, str, str, str]], bars: list[tuple[str, int]], bar_title: str):
    """cards: (라벨, 값, 단위, 보조문구). bars: (이름, 값)."""
    c = "".join(
        f'<div class="ais-card{" tint" if i == 0 else ""}"><span class="l">{_h(l)}</span>'
        f'<span class="v">{_h(v)}<small>{_h(u)}</small></span><span class="d">{_h(d)}</span></div>'
        for i, (l, v, u, d) in enumerate(cards))
    mx = max((v for _, v in bars), default=1) or 1
    b = "".join(f'<div class="ais-bar"><span>{_h(n)}</span><span class="t"><i style="width:{v / mx * 100:.0f}%"></i></span>'
                f'<span class="r">{v}</span></div>' for n, v in bars)
    block(f'''<div class="ais-hero"><div class="h1">{_h(title)}</div><div class="lead">{_h(lead)}</div>
<div class="ais-dash"><div class="hi">{_h(dash_title)}</div><div class="hi-sub">{_h(dash_sub)}</div>
<div class="ais-cards">{c}</div><div class="ais-bars"><div class="ttl">{_h(bar_title)}</div>{b}</div></div></div>''')


# ---------------------------------------------------------------- 가치사슬 일러스트
def chip(label: str, cls: str = "", prio: int | None = None) -> str:
    dot = f'<i class="ais-dot p{prio}"></i>' if prio else ""
    return f'<span class="ais-chip {cls}">{dot}{_h(label)}</span>'


def chain(stages: list[str], info: dict[str, dict], chips: dict[str, list[str]], legend: str = ""):
    """단계 카드(일러스트·무슨 일·돈의 흐름·장부)를 화살표로 잇는다. chips: 단계 → chip() HTML 목록."""
    parts = []
    for i, s in enumerate(stages, 1):
        d = info.get(s, {})
        rows = "".join(f'<div class="row"><b>{k}</b>{_h(d[f])}</div>'
                       for k, f in (("돈", "money"), ("장부", "books")) if d.get(f))
        parts.append(
            f'<div class="ais-stage"><div class="art">{art.img(d.get("icon", ""), 72)}</div>'
            f'<div><span class="pill">STEP {i:02d}</span></div><div class="nm">{_h(s)}</div>'
            + (f'<div class="do">{_h(d["do"])}</div>' if d.get("do") else "")
            + rows + f'<div class="chips">{"".join(chips.get(s, []))}</div></div>')
    block('<div class="ais-chain">' + '<div class="ais-arrow">→</div>'.join(parts) + "</div>"
          + (f'<div class="ais-legend">{legend}</div>' if legend else ""))


PRIO_LEGEND = ('<span><i class="ais-dot p1"></i>우선 검토 제안</span><span><i class="ais-dot p2"></i>중간</span>'
               '<span><i class="ais-dot p3"></i>참고</span><span>· 돈 = 돈의 흐름, 장부 = 재무제표에 남는 것</span>')
STATUS_LEGEND = (f'{chip("회사 공시로 확인", "fact")}{chip("산업자료 추론", "inf")}{chip("자료로 확인 불가", "unv")}'
                 '<span>· 점 색 = 검토 우선순위(제안)</span>')


# ---------------------------------------------------------------- 산업·본부 카드
def industry_head(p: dict):
    draft = p.get("review", {}).get("status") == "draft"
    tag = ' <span class="pill" style="background:#FFE7C2;color:#7A4A00">초안 · 검토 필요</span>' if draft else ""
    block(f'''<div class="ais-ind"><div class="art">{art.industry_img(p["key"], 52)}</div>
<div><div class="nm">{_h(p["name"])}{tag}</div><div class="sm">{_h(p["summary"])}</div></div></div>
<div class="ais-mini">{" → ".join(_h(s) for s in p["value_chain"])}</div>''')


def division_head(d: dict, covered: int, total: int):
    fn = d.get("kind") == "function"
    meter = "" if fn else (f'<div class="meter"><i style="width:{covered / total * 100 if total else 0:.0f}%"></i></div>'
                           f'<div class="ab" style="margin-top:4px">지식베이스 준비 {covered}/{total} 섹터</div>')
    ex = f' · 예: {", ".join(_h(x) for x in d["examples"])}' if d.get("examples") else ""
    note = f'<div class="note">⚠ {_h(d["note"])}</div>' if d.get("note") else ""
    block(f'''<div class="ais-div" style="border:0;padding:0;background:transparent">
<div class="top"><span class="code">{_h(d["code"])}</span><span class="pill {'gray' if fn else ''}">{'기능 본부' if fn else '산업 본부'}</span></div>
<div class="nm">{_h(d["name"])}</div><div class="ab">{_h(d.get("about", ""))}{ex}</div>{meter}{note}</div>''')


# ---------------------------------------------------------------- 작동 원리
def flow():
    inputs = [("공시 원문", "OpenDART 사업보고서·재무제표"), ("공개 산업자료", "사용자가 업로드한 .txt"),
              ("산업 지식베이스", "사람이 검토한 특성·위험·질문"), ("감사 유형", "계속 / 초도")]
    steps = [("01", "정제·보안 게이트", "비공개 의심 문서 차단, 개인정보 마스킹", "CODE"),
             ("02", "산업 특성 찾기", "통제된 특성 목록 안에서만 후보 선택, 원문 인용 검증", "AI·KW"),
             ("03", "Risk Mapping", "특성 → 계정 → 주장 → 질문 연결은 지식베이스만 사용", "KB"),
             ("04", "재무 신호", "지표 계산·기준 비교, 계속기업 지표판", "CODE"),
             ("05", "특수관계자 교차점검", "두 공시의 표 추출 → 인용 검증 → 대사", "AI+CODE"),
             ("06", "확인 질문", "지식베이스 질문 + AI 제안(가드레일 통과분만)", "KB+AI")]
    outputs = [("산업 스냅샷", "가치사슬 위 특성 확인 상태"), ("Risk Map", "검토 우선순위 제안"),
               ("확인 질문", "목적·근거 포함"), ("재무 신호표", "정상·주의·위험·확인 필요"),
               ("브리핑", "Markdown·JSON·검토 기록")]
    li = lambda xs: "".join(f'<div class="it"><span>{_h(a)}<span class="s">{_h(b)}</span></span></div>' for a, b in xs)
    st_ = "".join(f'<div class="it"><span class="n">{n}</span><span style="flex:1">{_h(a)}<span class="s">{_h(b)}</span></span>'
                  f'<span class="pill {"ink" if t == "CODE" else ""}">{t}</span></div>' for n, a, b, t in steps)
    block(f'''<div class="ais-flow"><div class="col"><div class="ttl">입력</div>{li(inputs)}</div><div class="ar">→</div>
<div class="col main"><div class="ttl">처리</div>{st_}</div><div class="ar">→</div>
<div class="col"><div class="ttl">출력</div>{li(outputs)}</div></div>
<div class="ais-foot">숫자 계산과 위험 연결은 코드·지식베이스가 하고, AI는 요약·추출·질문 제안만 합니다.
AI가 실패하면 '위험 없음'이 아니라 '확인 필요'로 표시합니다.</div>''')
