"""산업 초안 만들기 — 상장사 3~5곳의 공시로 새 산업의 지식베이스 초안을 만든다.

흐름: ① 자료 모으기(코드: 사업의 내용·재무) → ② 참고자료 확인(코드) → ③ 초안(AI 또는 뼈대) → ④ 검증 → ⑤ 초안 저장
원칙: AI는 통제된 어휘 안에서 초안만 쓰고, 검증을 통과한 초안만 knowledge/drafts/에 '초안'으로 저장한다.
화면 규칙: 움직이는 효과(스피너 등)를 쓰지 않는다 — 진행 상황은 정적인 문구로만 보여준다.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st
import yaml

from scanner import kb, kb_draft, ksic
from scanner.analyze import AnalyzerError, make_analyzer
from scanner.collect import CollectError, DartCollector

st.caption("같은 산업의 상장사 3~5곳을 넣으면, 공시의 사업의 내용과 재무제표를 근거로 산업 지식베이스 초안을 만듭니다. "
           "초안은 감사인이 검토하기 전까지 '초안 · 검토 필요'로 표시됩니다.")

# ---------------- ① 입력 ----------------
with st.form("kb_builder"):
    c1, c2, c3 = st.columns([2, 2, 1])
    name = c1.text_input("산업 이름", placeholder="예: 보험업")
    key = c2.text_input("산업 키 (영문 소문자)", placeholder="예: insurance")
    prefix = c3.text_input("ID 접두어", placeholder="예: INS", max_chars=6)
    ksic_in = st.text_input("업종코드(KSIC) 접두어 — 쉼표로 구분", placeholder="예: 651",
                            help="이 코드로 시작하는 회사에 이 산업을 적용합니다. 가장 긴 접두어가 우선합니다.")
    companies = st.text_area("상장사 (한 줄에 한 곳, 3~5곳 권장)", placeholder="삼성생명\n한화생명\n교보생명", height=110)
    go = st.form_submit_button("자료 모으기", type="primary")

if go:
    names = [n.strip() for n in companies.splitlines() if n.strip()]
    if not (name and key and prefix and names):
        st.warning("산업 이름·키·접두어와 회사를 입력하세요.")
    else:
        dart_key = os.getenv("DART_API_KEY", "")
        msg = st.empty()   # 정적 진행 문구 (애니메이션 없음)
        sources, errors = [], []
        for i, n in enumerate(names, 1):
            msg.info(f"공시 수집 중 {i}/{len(names)}: {n}")
            try:
                sources.append(kb_draft.collect_company(DartCollector(dart_key), n))
            except (CollectError, Exception) as e:  # 한 곳 실패가 전체를 멈추지 않게
                errors.append(f"{n}: {e}")
        msg.empty()
        st.session_state.kbb = {"name": name, "key": key.strip(), "prefix": prefix.strip().upper(),
                                "ksic": [x.strip() for x in ksic_in.split(",") if x.strip()],
                                "sources": sources, "errors": errors, "raw": None, "ids": None}

state = st.session_state.get("kbb")
if not state:
    st.stop()
for e in state["errors"]:
    st.warning(e, title="수집 실패")
sources: list[kb_draft.CompanySource] = state["sources"]
if not sources:
    st.stop()

# ---------------- ② 참고자료 (코드) ----------------
st.subheader("1. 모은 자료")
st.dataframe(pd.DataFrame([{"회사": s.corp_name, "업종": ksic.label(s.induty_code), "사업의 내용(자)": len(s.business),
                            "재무제표": "있음" if s.financials else "없음"} for s in sources]),
             hide_index=True, alt="초안에 쓰인 회사별 자료 현황")

st.subheader("2. 참고자료")
c1, c2 = st.columns(2)
with c1.container(border=True, height="stretch"):
    st.markdown("**산업 용어 후보** (2곳 이상에서 나온 용어)")
    kw = kb_draft.keyword_candidates(sources)
    st.dataframe(pd.DataFrame(kw, columns=["용어", "회사 수", "빈도"]), hide_index=True, alt="산업 판별 키워드 후보")
    st.caption("범용어는 오탐을 만듭니다. 그 산업에서만 쓰는 용어만 고르세요.")
with c2.container(border=True, height="stretch"):
    st.markdown("**재무 지표 실제 분포** → 확인 신호 기준 제안")
    prof = kb_draft.metric_profile(sources)
    st.dataframe(pd.DataFrame([{"지표": r["지표"], **{k: round(v, 1) for k, v in r["최근값"].items()},
                                "제안 기준": r["제안 기준"]} for r in prof]),
                 hide_index=True, alt="동종사 재무 지표 최근값과 제안 기준")
    st.caption("제안 기준 = 동종사 전년 대비 변동폭의 75% 분위 (하한 있음). 표본이 작으니 참고값입니다.")

# ---------------- ③ 초안 ----------------
st.subheader("3. 초안")
has_ai = bool(os.getenv("ANTHROPIC_API_KEY"))
if not has_ai:
    st.info("ANTHROPIC_API_KEY가 없어 AI 초안 대신 **뼈대**를 만듭니다. TODO를 채운 뒤 지식베이스 파일에 직접 붙여 넣으세요.")
    st.code(kb_draft.skeleton(state["key"], state["name"], state["prefix"], state["ksic"], sources, kw, prof),
            language="yaml")
    st.stop()

if st.button("AI 초안 작성", type="primary", key="kbb_draft"):
    note = st.empty()
    note.info("AI 초안 작성 중 — 수십 초 걸릴 수 있습니다.")
    try:
        state["raw"], state["ids"] = kb_draft.ai_draft(make_analyzer(True, effort="high"), state["name"], sources)
    except AnalyzerError as e:
        st.error(str(e))
    note.empty()

if not state.get("raw"):
    st.stop()

block, notes = kb_draft.assemble(state["key"], state["name"], state["prefix"], state["ksic"], state["raw"],
                                 prof, state["ids"])
for n in notes:
    st.warning(n, title="조립 중 조치")

# ---------------- ④ 검증 · ⑤ 저장 ----------------
st.subheader("4. 검증")
errs = kb_draft.validate(state["key"], block)
if errs:
    st.error("\n".join(f"- {e}" for e in errs), title="저장할 수 없음 — 규칙 위반")
else:
    st.success("지식베이스 규칙을 모두 통과했습니다.", title="검증 통과")
st.code(yaml.safe_dump({state["key"]: block}, allow_unicode=True, sort_keys=False, width=120), language="yaml")

if st.button("초안으로 저장", disabled=bool(errs), key="kbb_save",
             help="knowledge/drafts/에 저장합니다. 본 지식베이스 파일은 바꾸지 않습니다."):
    path = kb_draft.save(state["key"], block)
    st.success(f"{path.name}에 저장했습니다. 이제 기업 분석에서 이 산업이 '초안'으로 적용됩니다. "
               f"검토가 끝나면 내용을 knowledge/industry_kb.yaml로 옮기고 review 줄을 지우세요.")
    st.caption(f"지식베이스 산업 수: {len(kb.industries())}")
