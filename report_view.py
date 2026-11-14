"""② 사업보고서 요약 — DART 사업보고서 'II. 사업의 내용'을 그래프와 카드로 정리한다.

모든 문장·숫자는 공시 원문에서 그대로 가져온다 (요약문을 지어내지 않음).
구성: 회사 카드 → 한 줄로 보는 사업 → [부문 구성 도넛 | 섹션별 분량] → 숫자로 보는 사업
      → 보고서 속 산업 키워드(가치사슬 단계별 색) → 섹션 지도(단계 칩) → 섹션 상세(원문·표)
"""
from __future__ import annotations

import re
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

import illustrations as art
import ui
from scanner import catalog, kb, ksic
from scanner.models import Report
from scanner.report_parse import NUM_UNIT as _FIRST_NUM
from scanner.report_parse import keyword_counts, share_table, stage_keywords

MARKET = {"Y": "유가증권시장", "K": "코스닥", "N": "코넥스", "E": "기타(비상장)"}
SECTION_ICON = {"overview": "brand", "product": "package", "material": "groundbreak", "sales": "invoice",
                "risk": "repair", "rnd": "design", "etc": "contract"}
PALETTE = ["#2F7FE0", "#0B0B0C", "#A9CFF5", "#B45309", "#1F7A4D", "#5B4BC4", "#E0B400", "#9A9AA0"]


def _h(x) -> str:
    return escape(str(x or ""))


def _date(s: str) -> str:
    return f"{s[:4]}.{s[4:6]}.{s[6:8]}" if s and len(s) == 8 and s.isdigit() else (s or "-")


def _md(text: str) -> str:
    """원문을 마크다운으로 안전하게: 수식($)·강조(*)·제목(#) 기호를 이스케이프, 소제목은 굵게."""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"([$*_#~`|<>\[\]])", r"\\\1", s)
        if re.match(r"^(?:[가-하]\.|\d{1,2}\)|[가-하]\)|\(\d{1,2}\)|\[[^\]]{1,20}\])\s*\S", line.strip()) and len(s) < 60:
            s = f"**{s}**"
        out.append(s)
    return "  \n".join(out)


def _stage_kws(r: Report) -> tuple[list[str], dict[str, list[str]]]:
    p = catalog.profile(r.snapshot.industry_key)   # 미지원 업종은 업종 일반형 템플릿
    return p["value_chain"], stage_keywords(p["traits"], p["value_chain"], p["stage_info"])


# ---------------------------------------------------------------- 1. 회사 카드
def company_card(r: Report):
    p = r.company_profile
    code = r.induty_code or p.get("induty_code", "")
    ind_art = art.industry_img(r.snapshot.industry_key, 60) if kb.is_supported(r.snapshot.industry_key) else art.img("complete", 60)
    if not p:  # 데모 등 DART 외 입력
        ui.block(f'''<div class="ais-plain"><div class="ais-ind"><div class="art">{ind_art}</div>
<div><div class="nm">{_h(r.company)}</div><div class="sm">{_h(ksic.label(code))} · DART 기업개황 없음(데모·업로드 자료)</div></div></div></div>''')
        return
    market = MARKET.get(p.get("corp_cls", ""), "")
    pills = "".join(f'<span class="pill {c}">{_h(t)}</span> ' for t, c in (
        (market, "ink"), (f"종목코드 {p['stock_code']}" if p.get("stock_code") else "", ""), (ksic.label(code), "gray")) if t)
    cells = [("대표이사", p.get("ceo_nm")), ("설립일", _date(p.get("est_dt", ""))),
             ("결산월", f"{p['acc_mt']}월" if p.get("acc_mt") else "-"), ("업종", ksic.division_name(code) or "-")]
    cell_html = "".join(f'<div class="ais-card"><span class="l">{_h(l)}</span><span class="v" style="font-size:18px">{_h(v)}</span></div>'
                        for l, v in cells)
    ui.block(f'''<div class="ais-plain">
<div class="ais-ind"><div class="art">{ind_art}</div><div style="min-width:0">
<div class="nm">{_h(p.get("corp_name") or r.company)} <span style="font-size:14px;font-weight:500;color:#6B6B6B">{_h(p.get("corp_name_eng"))}</span></div>
<div style="margin-top:6px">{pills}</div></div></div>
<div class="ais-cards" style="margin-top:14px">{cell_html}</div>
<div class="sub">{_h(p.get("adres"))} · 출처: {_h(p.get("report_nm"))} · 접수 {_h(_date(p.get("rcept_dt", "")))}</div></div>''')
    home = p.get("hm_url", "")
    with st.container(horizontal=True, gap="small"):
        if p.get("url"):
            st.link_button("DART 원문 보기", p["url"], icon=":material/open_in_new:")
        if home:
            st.link_button("회사 홈페이지", home if home.startswith("http") else f"https://{home}",
                           icon=":material/language:")


# ---------------------------------------------------------------- 2. 한 줄로 보는 사업
def overview_line(sections: list[dict]):
    ov = next((s for s in sections if s["key"] == "overview" and s["lead"]), None) or \
        next((s for s in sections if s["lead"]), None)
    if not ov:
        return
    lead = ov["lead"]
    ui.block(f'<div class="ais-quote-hero"><div class="tag">사업보고서 원문 · {_h(ov["title"])}</div>'
             f'<div class="txt">“{_h(lead[0])}”</div>'
             + (f'<div class="sub">{_h(" ".join(lead[1:]))}</div>' if len(lead) > 1 else "") + '</div>')


# ---------------------------------------------------------------- 3. 그래프
def share_donut(sections: list[dict]):
    sh = share_table(sections)
    if not sh:
        st.caption("부문·제품별 비중 표를 자동으로 찾지 못했습니다. 아래 섹션 상세의 표를 확인하세요.")
        return
    items = sorted(sh["items"], key=lambda x: -x["비중"])
    if len(items) > 7:
        items = items[:6] + [{"항목": "기타", "비중": round(sum(x["비중"] for x in items[6:]), 1)}]
    df = pd.DataFrame(items)
    order = list(df["항목"])
    color = alt.Color("항목:N", sort=order, scale=alt.Scale(domain=order, range=PALETTE[:len(order)]),
                      legend=alt.Legend(orient="right", title=None, labelLimit=160))
    arc = alt.Chart(df).mark_arc(innerRadius=62, outerRadius=104, cornerRadius=3, padAngle=.015).encode(
        theta=alt.Theta("비중:Q", stack=True), color=color, order=alt.Order("비중:Q", sort="descending"),
        tooltip=["항목:N", alt.Tooltip("비중:Q", format=".1f", title="비중(%)")])
    top = df.iloc[0]
    center = alt.Chart(pd.DataFrame({"t": [f"{top['비중']:.0f}%"]})).mark_text(fontSize=26, fontWeight=700).encode(text="t:N")
    sub = alt.Chart(pd.DataFrame({"t": [str(top["항목"])[:10]]})).mark_text(dy=20, fontSize=11, color="#6B6B6B").encode(text="t:N")
    st.altair_chart((arc + center + sub).properties(height=250), alt=f"{sh['section']} 표의 항목별 {sh['header']}")
    st.caption(f"출처: '{sh['section']}' 표의 '{sh['header']}' 열{(' · ' + sh['period']) if sh['period'] else ''}")


def section_volume(sections: list[dict]):
    df = pd.DataFrame([{"섹션": f"{s['no']}. {s['title']}", "글자 수": len(s["text"]), "표": len(s["tables"]),
                        "핵심 수치": len(s["facts"])} for s in sections])
    base = alt.Chart(df).encode(y=alt.Y("섹션:N", sort=list(df["섹션"]), title=None, axis=alt.Axis(labelLimit=170)))
    bar = base.mark_bar(cornerRadiusEnd=4, height=16, color="#0B0B0C").encode(
        x=alt.X("글자 수:Q", title="본문 글자 수", axis=alt.Axis(format="~s")),
        tooltip=["섹션:N", alt.Tooltip("글자 수:Q", format=","), "표:Q", "핵심 수치:Q"])
    tbl = base.transform_calculate(lbl="'표 ' + datum['표']").mark_text(
        align="left", dx=5, fontSize=11, color="#2F7FE0", fontWeight=600).encode(x="글자 수:Q", text="lbl:N")
    st.altair_chart((bar + tbl).properties(height=30 * len(df) + 30),
                    alt="사업의 내용 섹션별 본문 분량과 표 개수")


def keyword_chart(r: Report):
    stages, kws = _stage_kws(r)
    rows = []
    for stg in stages:
        for k, n in keyword_counts(r.business_sections, kws.get(stg, [])).items():
            if n:
                rows.append({"키워드": k, "언급": n, "가치사슬 단계": stg})
    if not rows:
        st.caption("지식베이스의 산업 키워드가 이 보고서에 나오지 않았습니다.")
        return
    df = pd.DataFrame(rows).sort_values("언급", ascending=False).drop_duplicates("키워드").head(14)
    used = [s for s in stages if s in set(df["가치사슬 단계"])]
    chart = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=14).encode(
        y=alt.Y("키워드:N", sort="-x", title=None),
        x=alt.X("언급:Q", title="사업보고서 언급 수", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("가치사슬 단계:N", sort=used, scale=alt.Scale(domain=used, range=PALETTE[:len(used)]),
                        legend=alt.Legend(orient="bottom", title="가치사슬 단계", columns=4)),
        tooltip=["키워드:N", "언급:Q", "가치사슬 단계:N"])
    st.altair_chart(chart.properties(height=24 * len(df) + 40),
                    alt=f"{r.company} 사업보고서에 나온 산업 키워드와 가치사슬 단계")


# ---------------------------------------------------------------- 4. 숫자로 보는 사업
def fact_cards(sections: list[dict], limit: int = 6):
    by_sec: dict[str, list[str]] = {}
    for s in sections:
        for f in s["facts"]:
            by_sec.setdefault(s["title"], []).append(f)
    picked, i = [], 0      # 섹션이 골고루 나오도록 라운드로빈
    while len(picked) < limit and any(i < len(v) for v in by_sec.values()):
        for t, v in by_sec.items():
            if i < len(v) and len(picked) < limit:
                picked.append((t, v[i]))
        i += 1
    if not picked:
        st.caption("숫자가 들어간 원문 문장을 찾지 못했습니다.")
        return
    cards = []
    for t, f in picked:
        m = _FIRST_NUM.search(f)
        cards.append(f'<div class="ais-card ais-fact"><span class="pill">{_h(t)}</span>'
                     f'<span class="v">{_h(m.group(0) if m else "")}</span>'
                     f'<span class="s">{_h(f[:150])}{"…" if len(f) > 150 else ""}</span></div>')
    ui.block(f'<div class="ais-cards" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">{"".join(cards)}</div>')


# ---------------------------------------------------------------- 5. 섹션 지도
def toc(r: Report, sections: list[dict]):
    stages, kws = _stage_kws(r)
    tiles = []
    for s in sections:
        first = s["lead"][0] if s["lead"] else (s["text"][:80] if s["text"] else "내용 없음")
        hit = [stg for stg in stages if sum(keyword_counts([s], kws.get(stg, [])).values())]
        chips = "".join(f'<span class="ais-chip inf">{_h(x)}</span>' for x in hit[:4])
        tiles.append(
            f'<div class="ais-card ais-toc">'
            f'<div class="hd">{art.img(SECTION_ICON.get(s["key"], ""), 40)}'
            f'<div><span class="pill">{s["no"]:02d}</span><div class="t">{_h(s["title"])}</div></div></div>'
            f'<div class="s">{_h(first[:90])}{"…" if len(first) > 90 else ""}</div>'
            + (f'<div class="chips">{chips}</div>' if chips else "")
            + f'<div class="m">표 {len(s["tables"])} · 핵심 수치 {len(s["facts"])} · {len(s["text"]):,}자</div></div>')
    ui.block(f'<div class="ais-cards" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr))">{"".join(tiles)}</div>')


# ---------------------------------------------------------------- 6. 섹션 상세
def _frame(rows: list[list[str]]) -> pd.DataFrame:
    head, body = rows[0], rows[1:] or [[""] * len(rows[0])]
    cols, seen = [], {}
    for c in head:
        c = c or "-"
        seen[c] = seen.get(c, 0) + 1
        cols.append(c if seen[c] == 1 else f"{c} ({seen[c]})")
    return pd.DataFrame(body, columns=cols)


def section_detail(sections: list[dict]):
    titles = [f"{s['no']}. {s['title']}" for s in sections]
    pick = st.pills("섹션", titles, default=titles[0], key="biz_sec", label_visibility="collapsed") or titles[0]
    s = sections[titles.index(pick)]
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1.container(border=True):
        if s["lead"]:
            st.markdown("**" + _md(" ".join(s["lead"])) + "**")
        with st.container(height=460, border=False):
            st.markdown(_md(s["text"]) or "_본문 없음_")
    with c2:
        if s["facts"]:
            with st.container(border=True):
                st.markdown("**이 섹션의 핵심 수치**")
                for f in s["facts"]:
                    st.markdown(f"- {_md(f)}")
        st.caption(f"표 {len(s['tables'])}개")
    for i, t in enumerate(s["tables"], 1):
        with st.expander(f"표 {i}" + (f" · {t['unit']}" if t["unit"] else "") + f" · {len(t['rows']) - 1}행",
                         expanded=i == 1):
            st.dataframe(_frame(t["rows"]), hide_index=True, alt=f"{s['title']} 표 {i}")


def render(r: Report):
    company_card(r)
    secs = r.business_sections
    if not secs:
        st.info("사업보고서 '사업의 내용'을 구조화하지 못했습니다. OpenDART 공시로 분석하면 섹션·표·핵심 수치가 정리됩니다.")
        return
    overview_line(secs)

    c1, c2 = st.columns(2, gap="medium")
    with c1.container(border=True, height="stretch"):
        st.markdown("**무엇으로 돈을 버나 — 부문·제품 구성**")
        share_donut(secs)
    with c2.container(border=True, height="stretch"):
        st.markdown("**보고서는 어디에 힘을 줬나 — 섹션별 분량**")
        section_volume(secs)

    ui.section("숫자로 보는 사업", "숫자가 들어간 원문 문장 — 섹션마다 골고루")
    fact_cards(secs)

    if _stage_kws(r)[0]:
        ui.section("보고서 속 산업 키워드", "가치사슬 단계·산업 특성 키워드가 몇 번 나오는지 — 색은 가치사슬 단계")
        with st.container(border=True):
            keyword_chart(r)

    ui.section("사업의 내용 지도", f"표준 소제목 {len(secs)}개 · 표 {sum(len(s['tables']) for s in secs)}개 · "
                                  "칩 = 그 섹션이 다루는 가치사슬 단계")
    toc(r, secs)
    ui.section("섹션 상세", "원문과 표를 섹션별로")
    section_detail(secs)
