"""기업 분석 페이지의 부품 — 첫 화면(검색 전), 분석 후 회사 머리, Risk Map·질문·자료 요청.

목적: 감사인이 처음 맡은 회사를 '산업 특성 → 위험신호 → 확인 질문·자료 요청'까지 한 화면에서 잡게 한다.
모든 숫자는 Report에서 그대로 집계한다 (새 판단을 만들지 않음).
"""
from __future__ import annotations

import base64
import json
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import illustrations as art
import industry_view as iv
import snapshot_view
import ui
from scanner import catalog, kb
from scanner.brief import PRIORITY_ICON
from scanner.models import Report

RUNS_DIR = Path(__file__).resolve().parent / "runs"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".webp": "image/webp"}
QUICK = ["삼성전자", "현대자동차", "POSCO홀딩스", "셀트리온", "NAVER", "신한지주"]
DECISIONS = ["미검토", "절차에 반영", "보류", "해당 없음"]
ORIGIN_LABEL = {"KB": "지식베이스", "AI": "AI 제안", "FIN": "재무 신호", "XCHK": "교차점검"}


def _h(x) -> str:
    return escape(str(x or ""))


# =====================================================================
# 검색 전 첫 화면
# =====================================================================
def quick_chips(enabled: bool):
    """자주 보는 상장사로 바로 검색. 검색창(dart_q)을 채우는 콜백이라 위젯보다 먼저 값이 들어간다."""
    def _set(name: str):
        st.session_state.dart_q = name
        st.session_state.pop("dart_pick", None)

    with st.container(horizontal=True, gap="small"):
        st.caption("바로 검색")
        for n in QUICK:
            st.button(n, key=f"quick_{n}", on_click=_set, args=(n,), disabled=not enabled, type="tertiary")


def kb_stats() -> dict[str, int]:
    """첫 화면 숫자 — 지식베이스에서 그대로 센다 (꾸민 숫자 없음)."""
    inds = kb.industries()
    traits = [t for v in inds.values() for t in v.get("traits", [])]
    risks = [r for t in traits for r in t.get("risks", [])]
    return {"industries": len(inds), "traits": len(traits), "risks": len(risks),
            "questions": sum(len(r.get("questions", [])) for r in risks)}


HERO_STEPS = [("01", "사업보고서를 읽고", "DART '사업의 내용'·재무제표·최근 공시를 가져옵니다"),
              ("02", "가치사슬에 얹고", "산업이 돈을 버는 단계마다 이 회사 공시 문장을 붙입니다"),
              ("03", "감사 질문으로", "단계에서 생기는 회계 판단을 검토 영역·질문·자료 요청으로 바꿉니다")]


def opendart_logo() -> str:
    """assets/opendart_logo.(png|svg|jpg|webp)가 있으면 그 이미지(data URI), 없으면 글자형 워드마크.
    공식 로고 파일은 저장소에 넣지 않았다(사용 조건 확인 후 직접 넣기)."""
    for ext, mime in LOGO_TYPES.items():
        f = ASSETS_DIR / f"opendart_logo{ext}"
        if f.exists():
            data = base64.b64encode(f.read_bytes()).decode("ascii")
            return f'<img class="logo-img" src="data:{mime};base64,{data}" alt="OpenDART">'
    return '<div class="wm" role="img" aria-label="OpenDART"><span class="o">Open</span><span class="d">DART</span></div>'


def source_card() -> str:
    chips = "".join(f'<span>{t}</span>' for t in ("사업보고서 · 사업의 내용", "재무제표 3개년", "최근 1년 공시", "기업개황 · 업종코드"))
    return (f'<div class="src"><div class="top">{opendart_logo()}'
            '<div class="who">금융감독원 전자공시 OpenAPI<br><b>모든 분석의 출처</b></div></div>'
            f'<div class="chips">{chips}</div></div>')


def hero_html() -> str:
    """검색 전 첫 화면 — 정적(애니메이션 없음). 왼쪽 메시지·3단계, 오른쪽 지식베이스 산업 타일."""
    inds = kb.industries()
    s = kb_stats()
    tiles = "".join(f'<div class="t"><span class="ic">{art.industry_img(k, 30)}</span><span class="n">{_h(v["name"])}</span>'
                    f'<span class="g">{_h(v.get("group", ""))}</span></div>' for k, v in inds.items())
    steps = "".join(f'<div class="s"><b>{n}</b><div><div class="st">{_h(t)}</div><div class="sd">{_h(d)}</div></div></div>'
                    for n, t, d in HERO_STEPS)
    return (
        '<div class="ais-hero3"><div class="l">'
        '<div class="eyebrow">AI AUDIT INDUSTRY SCANNER · 상장사 공개 공시 기반</div>'
        '<div class="h1">산업을 알면,<br><em>위험이 보인다.</em></div>'
        '<div class="lead">상장사 이름 하나로 DART 사업보고서를 읽어, 그 산업이 돈을 버는 방식과 '
        '감사에서 먼저 볼 곳을 정리합니다.</div>'
        f'{source_card()}<div class="steps">{steps}</div></div>'
        f'<div class="r"><div class="cap"><span>산업 지식베이스 {len(inds)}</span>'
        f'<span>업종 일반형 가치사슬 {len(kb.generic_chains())}</span></div>'
        f'<div class="grid">{tiles}</div>'
        f'<div class="foot">검토 영역 {s["risks"]}개 · 감사 질문 {s["questions"]}개 · 근거는 모두 공시 원문</div></div></div>')


def hero():
    ui.block(hero_html())


def recent_runs(limit: int = 6) -> list[dict]:
    """runs/에 저장된 최근 분석 (회사별 최신 1건). 형식이 맞지 않는 옛 파일은 건너뛴다."""
    out, seen = [], set()
    for p in sorted(RUNS_DIR.glob("*.json"), reverse=True)[:80]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = d.get("company")
        if not name or name in seen or not d.get("company_profile"):   # 데모·업로드 결과는 목록에서 뺀다
            continue
        seen.add(name)
        out.append({"path": p, "company": name, "at": d.get("generated_at", "")[:16].replace("T", " "),
                    "industry": d.get("snapshot", {}).get("industry_name", ""), "mode": d.get("mode", "")})
        if len(out) >= limit:
            break
    return out


def open_run(path: Path) -> str | None:
    """저장된 분석을 다시 연다. 실패하면 이유를 돌려준다."""
    try:
        r = Report.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:  # 옛 형식 등
        return f"이 기록은 현재 형식과 맞지 않아 열 수 없습니다: {type(e).__name__}"
    st.session_state.report = r
    st.session_state.review = {}
    for k in [k for k in st.session_state if str(k).startswith(("mat_", "d_", "m_"))]:
        del st.session_state[k]
    return None


def recent_panel():
    runs = recent_runs()
    st.markdown("**최근 분석 다시 열기**")
    if not runs:
        st.caption("아직 저장된 분석이 없습니다.")
        return
    for i, x in enumerate(runs):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.markdown(f"**{x['company']}**  \n:small[{x['industry']} · {x['at']} · {x['mode']}]")
        if c2.button("열기", key=f"open_run_{i}", icon=":material/history:"):
            err = open_run(x["path"])
            if err:
                st.error(err)
            else:
                st.rerun()


# =====================================================================
# 분석 후 머리
# =====================================================================
def header(r: Report):
    """회사 머리 — 이름·보고서·분류 배지, 그리고 이 산업이 무엇으로 돈을 버는지(요약 + 가치사슬 띠)."""
    key = r.snapshot.industry_key
    supported = kb.is_supported(key)
    p = r.company_profile
    icon = art.industry_img(key, 52) if supported else art.img("complete", 52)
    tpl = kb.industry(key).get("template", "")
    summ = (kb.industries()[key].get("summary", "") if supported
            else f"산업 지식베이스에 아직 없는 업종이라 '{tpl or '업종 일반형'}' 가치사슬로 읽습니다. 회사 고유의 사업 구조는 사업보고서에서 확인하세요.")
    chain = catalog.profile(key)["value_chain"] or list(r.snapshot.value_chain)
    strip = "".join(f'<span class="st"><b>{i:02d}</b>{_h(x)}</span>' for i, x in enumerate(chain, 1))
    meta = " · ".join(x for x in [p.get("report_nm") or "데모·업로드 자료", r.generated_at[:10],
                                  "공시·지식베이스 분석", r.engagement] if x)
    ui.block(f'<div class="ais-co"><div class="art">{icon}</div><div class="bd">'
             f'<div class="nm">{_h(r.company)}<span class="ind">{_h(r.snapshot.industry_name)}</span></div>'
             f'<div class="meta">{_h(meta)}</div><div class="sum">{_h(summ)}</div>'
             + (f'<div class="strip">{strip}</div>' if strip else "") + '</div></div>')
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(snapshot_view.classification_badges(r.induty_code, key))
        st.space("stretch")
        if supported and st.button(f"{r.snapshot.industry_name} 산업 깊이 보기", icon=":material/account_tree:",
                                   key="to_industry", type="tertiary"):
            st.session_state.industry = key
            st.switch_page("app_pages/industry.py")


# =====================================================================
# Risk Map · 질문 · 자료 요청
# =====================================================================
def risk_heatmap(r: Report):
    rows = [{"계정": a, "경영진 주장": s, "검토 영역": k.title, "우선순위": k.priority}
            for k in r.risks for a in k.accounts for s in k.assertions]
    iv.heatmap_from_rows(rows, f"{r.company}의 검토 영역이 걸린 계정과 경영진 주장")


def question_rows(r: Report) -> pd.DataFrame:
    return pd.DataFrame([{"우선": PRIORITY_ICON[k.priority], "검토 영역": k.title, "질문": q.question,
                          "출처": ORIGIN_LABEL.get(q.origin, q.origin), "목적": q.purpose,
                          "확인": False, "답변·메모": ""}
                         for k in r.risks for q in k.questions])


def pbc_rows(r: Report) -> pd.DataFrame:
    """검토 영역별 '추가 확인 자료'를 자료 기준으로 모은 요청 목록 (PBC: Prepared By Client)."""
    by: dict[str, dict] = {}
    for k in r.risks:
        for d in k.evidence_docs:
            x = by.setdefault(d, {"자료": d, "우선": k.priority, "관련 검토 영역": []})
            x["우선"] = min(x["우선"], k.priority)
            x["관련 검토 영역"].append(k.title)
    rows = sorted(by.values(), key=lambda x: (x["우선"], x["자료"]))
    return pd.DataFrame([{"우선": PRIORITY_ICON[x["우선"]], "자료": x["자료"],
                          "관련 검토 영역": ", ".join(dict.fromkeys(x["관련 검토 영역"])),
                          "상태": "요청 전", "담당": "", "기한": ""} for x in rows])


def questions_and_pbc(r: Report):
    st.caption("질문과 요청 자료는 표에서 바로 체크·메모할 수 있고, CSV로 내려받아 조서에 붙일 수 있습니다.")
    q = question_rows(r)
    origin = st.pills("출처", list(ORIGIN_LABEL.values()), selection_mode="multi",
                      default=list(ORIGIN_LABEL.values()), key="q_origin")
    q_view = q[q["출처"].isin(origin or list(ORIGIN_LABEL.values()))]
    with st.container(horizontal=True, gap="small"):
        for name in ORIGIN_LABEL.values():
            st.badge(f"{name} {int((q['출처'] == name).sum())}", color="gray")
    edited_q = st.data_editor(
        q_view, hide_index=True, key="q_editor", disabled=["우선", "검토 영역", "질문", "출처", "목적"],
        column_config={"질문": st.column_config.TextColumn(width="large"),
                       "확인": st.column_config.CheckboxColumn(width="small"),
                       "우선": st.column_config.TextColumn(width="small")},
        alt="검토 영역별 확인 질문 체크리스트")
    st.download_button("질문 체크리스트 (CSV)", edited_q.to_csv(index=False).encode("utf-8-sig"),
                       f"{r.company}_questions.csv", icon=":material/download:")

    ui.section("자료 요청 목록 (PBC)", "검토 영역마다 필요한 자료를 자료 기준으로 묶었습니다")
    pbc = pbc_rows(r)
    edited_p = st.data_editor(
        pbc, hide_index=True, key="pbc_editor", disabled=["우선", "자료", "관련 검토 영역"],
        column_config={"상태": st.column_config.SelectboxColumn(options=["요청 전", "요청함", "수령", "검토 완료"]),
                       "기한": st.column_config.TextColumn(help="예: 2026-12-15"),
                       "관련 검토 영역": st.column_config.TextColumn(width="large")},
        alt="회사에 요청할 자료 목록")
    st.download_button("자료 요청 목록 (CSV)", edited_p.to_csv(index=False).encode("utf-8-sig"),
                       f"{r.company}_PBC.csv", icon=":material/download:")
