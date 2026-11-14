"""기업 분석 페이지 — 처음 맡은 회사의 산업 특성을 공시로 확인하고 위험신호·확인 질문·자료 요청으로 잇는다.

구성: 회사 고르기(분석 후 접힘) → 회사 머리(산업 요약·가치사슬 띠) → 가치사슬 × 공시 · 사업보고서 요약
      → 공시 뉴스(최근 주요 공시) → 감사로 잇기(Risk Map · 질문·자료 요청 · 재무·중요성 · 특수관계자 · 근거·검증) → 내보내기
"""
from __future__ import annotations

import os
import time

import pandas as pd
import streamlit as st

import company_view
import disclosure_view
import fin_view
import industry_lens
import mat_view
import report_view
import rpt_view
import snapshot_view
from scanner import collect, kb, materiality
from scanner.analyze import AnalyzerError, make_analyzer
from scanner.brief import PRIORITY_ICON, to_markdown
from scanner.evaluate import RUBRIC, auto_metrics, load_human_eval, save_human_eval
from scanner.models import CLAIM_LABEL, Report, StepLog
from scanner.pipeline import export_json, run, source_label
from snapshot_view import TYPE_COLOR

# ---------------- 사이드바: 꼭 필요한 설정만 ----------------
HAS_DART, HAS_CLAUDE = bool(os.getenv("DART_API_KEY")), bool(os.getenv("ANTHROPIC_API_KEY"))
with st.sidebar:
    st.header("설정")
    st.markdown((":green-badge[OpenDART 연결됨]" if HAS_DART else ":red-badge[DART_API_KEY 없음]") + " "
                + (":green-badge[Claude 연결됨]" if HAS_CLAUDE else ":gray-badge[Claude 키 없음 · 오프라인]"))
    use_llm = st.toggle("Claude로 분석", value=HAS_CLAUDE, disabled=not HAS_CLAUDE,
                        help="끄면 지식베이스·키워드·업종 일반형 가치사슬로 오프라인 분석합니다 (가치사슬·공시 문장 연결은 오프라인에서도 동작).")
    effort = st.select_slider("분석 깊이", ["low", "medium", "high"], value="medium") if use_llm else "medium"
    engagement = st.segmented_control(
        "감사 유형", ["계속감사", "초도감사"], default="계속감사", key="engagement",
        help="초도감사를 고르면 기초잔액(감사기준서 510) 검토 영역이 추가됩니다.") or "계속감사"
    with st.expander("고급", icon=":material/tune:"):
        industry_override = st.selectbox(
            "산업 직접 지정", ["자동"] + list(kb.industries().keys()), key="industry_override",
            format_func=lambda k: "자동 (업종코드 기준)" if k == "자동" else
            f"{kb.industries()[k]['group']} · {kb.industries()[k]['name']}",
            help="업종코드 판별 대신 지정한 산업 지식베이스로 분석합니다.")
        up = st.file_uploader("공개 산업자료 추가 (.txt)", type=["txt"])
        up_title = up_pub = up_date = up_url = ""
        up_public = False
        if up is not None:
            up_title = st.text_input("자료명", placeholder="예: 2026 건설산업 동향")
            up_pub = st.text_input("발행기관", placeholder="예: 국토교통부")
            up_date = st.text_input("발행일", placeholder="2026-05-15")
            up_url = st.text_input("URL")
            up_public = st.checkbox("공개된 자료이며 고객 비공개 정보를 포함하지 않음을 확인합니다")
    st.caption(f"상장사 공개 공시만 사용 · 지식베이스 v{kb.kb_version()}")

@st.cache_data(ttl=86400, max_entries=200, show_spinner="DART 기업 목록에서 찾는 중…")
def dart_search(q: str) -> list[dict]:
    return collect.DartCollector(os.getenv("DART_API_KEY", "")).search_corps(q)


@st.cache_data(ttl=86400, max_entries=200, show_spinner=False)
def dart_info(corp_code: str) -> dict:
    return collect.DartCollector(os.getenv("DART_API_KEY", "")).company_info(corp_code)


report: Report | None = st.session_state.get("report")
st.session_state.setdefault("review", {})
corp_code = ""

# ---------------- 회사 고르기: 분석 전에는 크게, 분석 후에는 접어서 결과에 화면을 준다 ----------------
if report:
    picker = st.expander("다른 회사 분석하기", icon=":material/search:")
else:
    company_view.hero()
    picker = st.container()

with picker:
    left, right = st.columns([3, 2], gap="medium")
    with left.container(border=True, height="stretch"):
        st.markdown("**회사 고르기**")
        company = ""
        if not HAS_DART:
            st.error(".env에 DART_API_KEY를 넣으면 상장사를 검색할 수 있습니다 (OpenDART에서 무료 발급).")
        else:
            company_view.quick_chips(enabled=True)
            q = st.text_input("상장사 검색", placeholder="예: 삼성전자, POSCO홀딩스, 카카오", key="dart_q",
                              help="유가증권·코스닥·코넥스 상장사만 검색합니다. 이름이 비슷한 회사가 여럿이면 후보 중에서 고르세요.")
            if q.strip():
                try:
                    cands = dart_search(q.strip())
                except collect.CollectError as e:
                    st.error(str(e))
                    cands = []
                if not cands:
                    st.warning(f"'{q}'와(과) 일치하는 상장사를 찾지 못했습니다. 비상장 회사는 검색하지 않습니다.")
                else:
                    by_code = {c["corp_code"]: c for c in cands}
                    corp_code = st.selectbox(f"상장사 후보 {len(cands)}곳 — 분석할 회사를 고르세요", list(by_code),
                                             format_func=lambda k: collect.corp_label(by_code[k]), key="dart_pick")
                    company = by_code[corp_code]["corp_name"]
                    try:
                        info = dart_info(corp_code)
                        if collect.is_listed(info):
                            st.markdown(f":gray-badge[{collect.LISTED_CLS[info['corp_cls']]}]")
                            snapshot_view.classification_preview(info.get("induty_code", ""), industry_override)
                        else:  # 종목코드는 남아 있지만 상장폐지된 회사
                            st.warning(f"'{company}'은(는) 현재 상장사가 아닙니다(상장폐지 등). 다른 후보를 고르세요.")
                            company = ""
                    except collect.CollectError as e:
                        st.caption(f"기업개황을 불러오지 못했습니다: {e}")
        start = st.button("산업 이해 시작", type="primary", disabled=not company, key="start",
                          icon=":material/play_arrow:", width="stretch")
    with right.container(border=True, height="stretch"):
        company_view.recent_panel()

if start:
    try:
        t0 = time.perf_counter()
        docs, meta = collect.DartCollector(os.getenv("DART_API_KEY", "")).collect(company, corp_code=corp_code)
        if up is not None:
            if not up_public:
                st.warning("업로드 자료의 공개 여부가 확인되지 않아 분석에서 제외했습니다.")
            else:
                docs.append(collect.uploaded_doc(f"S{len(docs) + 1:02d}", up_title or up.name,
                                                 up_pub or "사용자 업로드", up_date, up_url,
                                                 up.getvalue().decode("utf-8", errors="replace")))
        collect_step = StepLog(step="1. 데이터 수집", started="", seconds=round(time.perf_counter() - t0, 2),
                               note=f"문서 {len(docs)}건, 재무제표 {'있음' if meta.get('financials') else '없음'}")
        with st.spinner("분석 중…"):
            new = run(meta.get("corp_name") or company, docs, meta,
                      make_analyzer(use_llm, effort=effort),
                      industry_key=None if industry_override == "자동" else industry_override,
                      financials=meta.get("financials"), engagement=engagement)
        new.steps.insert(0, collect_step)
        st.session_state.report = new
        st.session_state.review = {}
        # 새 회사는 도구 제안값·검토 기록을 비우고 다시 시작한다
        for k in [k for k in st.session_state if str(k).startswith(("mat_", "d_", "m_"))]:
            del st.session_state[k]
        st.rerun()
    except (collect.CollectError, AnalyzerError, ValueError) as e:
        st.error(str(e))

if not report:
    st.stop()

# ---------------- 분석 결과 ----------------
show_claims = snapshot_view.show_claims
s = report.snapshot
if report.cleaning.blocked_docs:
    st.warning("보안 게이트: 비공개 자료로 의심되어 분석에서 제외 → " + "; ".join(report.cleaning.blocked_docs))
for w in report.warnings:
    st.warning(w, title="확인 필요")

# 회사 머리 → 산업 이해(가치사슬 × 사업보고서)가 앞, 감사로 잇는 도구가 뒤
company_view.header(report)
disc_rows, disc_msg = disclosure_view.load(report)
disclosure_view.strip(report, disc_rows, disc_msg)

tabs = st.tabs([":material/account_tree: 가치사슬 × 공시", ":material/description: 사업보고서 요약",
                ":material/newspaper: 공시 뉴스", ":material/flag: Risk Map", ":material/checklist: 질문·자료 요청",
                ":material/monitoring: 재무·중요성", ":material/group: 특수관계자", ":material/fact_check: 근거·검증"])

# 중요성은 Risk Map의 재무 신호 표시에 쓰이므로 먼저 계산한다 (화면 위치는 '재무·중요성' 탭)
with tabs[5]:
    mat = mat_view.panel(report)
    sig_levels = materiality.signal_levels(report, mat) if mat else {}
    fin_view.render(report)

with tabs[0]:
    industry_lens.render(report)

with tabs[1]:
    report_view.render(report)

with tabs[2]:
    disclosure_view.render(report, disc_rows, disc_msg)

with tabs[3]:
    st.caption("우선순위는 '어디부터 검토할지'에 대한 제안이며 위험평가 결과가 아닙니다. "
               "계정·주장 연결은 검토된 지식베이스에서만 가져옵니다.")
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1.container(border=True):
        st.markdown("**계정 × 경영진 주장 지도** — 칸 색은 그 칸에 걸린 가장 높은 우선순위")
        company_view.risk_heatmap(report)
    with c2.container(border=True):
        st.markdown("**검토 영역 요약**")
        st.dataframe(pd.DataFrame([{"우선": PRIORITY_ICON[k.priority], "검토 영역": k.title, "근거": k.basis,
                                    "재무 신호": sum(x.triggered for x in k.fin_signals), "질문": len(k.questions)}
                                   for k in report.risks]),
                     hide_index=True, alt="검토 영역별 우선순위·근거·재무 신호·질문 수")
    for k in report.risks:
        fin_hit = [x for x in k.fin_signals if x.triggered]
        tag = " · 📈 재무 신호" if fin_hit else ""
        if any(sig_levels.get(id(x)) in ("계획 중요성 이상", "수행 중요성 이상") for x in fin_hit):
            tag += " · 💰 수행 중요성 이상"
        decided = st.session_state.get(f"d_{k.risk_id}") or "미검토"
        with st.expander(f"{PRIORITY_ICON[k.priority]} {k.title} — {k.basis}{tag} · [{decided}]",
                         expanded=k.priority == 1 and decided == "미검토"):
            a, b = st.columns([3, 2], gap="medium")
            with a:
                st.markdown(f"**산업 특성** {k.trait}")
                st.markdown(f"**잠재적 위험** {k.potential_risk}")
                st.markdown(" ".join(f":violet-badge[{x}]" for x in k.accounts) + "  \n"
                            + " ".join(f":gray-badge[{x}]" for x in k.assertions)
                            + f"  \n:small[참고 기준 {', '.join(k.references)}]")
                for e in k.trait_evidence:
                    st.markdown(f":{TYPE_COLOR[e.claim_type]}-badge[{CLAIM_LABEL[e.claim_type]}] {e.rationale} "
                                + " ".join(f"`{x}`" for x in e.source_ids))
                    for f in e.flags:
                        st.caption(f"⚠️ {f}")
                for x in k.fin_signals:
                    vals = " → ".join("N/A" if v is None else f"{v:,.1f}" for v in x.values.values())
                    st.markdown(f"**{x.metric}** ({x.unit}) {vals}  \n{fin_view.signal_status(x)}")
            with b.container(border=True):
                st.markdown("**감사인 검토**")
                st.session_state.review[k.risk_id] = {
                    "decision": st.segmented_control("결정", company_view.DECISIONS, default="미검토",
                                                     key=f"d_{k.risk_id}", label_visibility="collapsed") or "미검토",
                    "memo": st.text_area("검토 의견", key=f"m_{k.risk_id}", height=90,
                                         placeholder="예: 진행률 산정표 요청, 주요 현장 3곳 표본"),
                }
                if k.questions:
                    st.caption(f"확인 질문 {len(k.questions)}개 · 요청 자료 {len(k.evidence_docs)}개 → '질문·자료 요청' 탭")

with tabs[4]:
    company_view.questions_and_pbc(report)

with tabs[6]:
    rpt_view.render(report)

with tabs[7]:
    view = st.segmented_control("보기", ["출처·원문", "검증 지표·사람 평가", "처리 로그"], default="출처·원문",
                                key="evidence_view", label_visibility="collapsed") or "출처·원문"
    if view == "출처·원문":
        c1, c2 = st.columns(2, gap="medium")
        with c1.container(border=True):
            st.markdown("**출처**")
            for d in report.sources:
                st.markdown(f"- `{d.doc_id}` {source_label(report, d.doc_id)} {d.url} ({d.scope})")
            if report.financials:
                f = report.financials
                st.markdown(f"- `{f.source_id}` {source_label(report, f.source_id)} {f.url} (financial)")
            st.markdown("**확인되지 않은 사항 (Unverified)**")
            show_claims(s.information_gaps)
        with c2.container(border=True):
            st.markdown("**원문 청크**")
            cid = st.selectbox("청크 ID", [c.chunk_id for c in report.chunks])
            st.text_area("원문", next(c.text for c in report.chunks if c.chunk_id == cid), height=320, disabled=True)
    elif view == "검증 지표·사람 평가":
        c1, c2 = st.columns([2, 3], gap="medium")
        with c1.container(border=True):
            st.markdown("**자동 지표 (이번 실행)**")
            am = auto_metrics(report)
            st.dataframe(pd.DataFrame({"지표": list(am), "값": [str(v) for v in am.values()]}),
                         hide_index=True, alt="이번 실행의 자동 검증 지표")
        with c2.container(border=True):
            st.markdown("**사람 평가 — 기존 방식 vs MVP**")
            with st.form("eval"):
                method = st.segmented_control("평가 대상", ["MVP", "기존 방식(직접 조사)"], default="MVP")
                evaluator = st.text_input("평가자")
                minutes = st.number_input("산업 이해에 걸린 시간(분)", min_value=0.0, step=5.0)
                scores = {k: st.slider(f"{k} — {q}", 1, 5, 3) for k, q in RUBRIC.items()}
                missed = st.text_input("누락된 주요 특성")
                false_risks = st.text_input("근거 없는 위험(환각)")
                note = st.text_area("메모")
                if st.form_submit_button("평가 저장"):
                    save_human_eval(report.company, method or "MVP", evaluator, minutes, scores, missed,
                                    false_risks, note)
                    st.success("eval/results.csv에 저장했습니다.")
        rows = load_human_eval()
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, width="stretch")
            num = df[["방식", "소요시간(분)", *RUBRIC.keys()]].copy()
            for col in num.columns[1:]:
                num[col] = pd.to_numeric(num[col], errors="coerce")
            st.markdown("**방식별 평균**")
            st.dataframe(num.groupby("방식").mean().round(2), width="stretch")
    else:
        st.dataframe(pd.DataFrame([x.model_dump() for x in report.steps]), width="stretch")
        st.markdown(f"모드 **{report.mode}** {report.model} · 프롬프트 {report.prompt_version or '-'} · "
                    f"입력지문 `{report.input_fingerprint}`")
        st.markdown(f"정제: 청크 {report.cleaning.chunk_count}개, 마스킹 {report.cleaning.masked_items or '없음'}")
        st.markdown("**AI 통제(가드레일) 이벤트**")
        if report.guardrail_events:
            st.dataframe(pd.DataFrame([e.model_dump() for e in report.guardrail_events]), width="stretch")
        else:
            st.caption("이벤트 없음")

# ---------------- 내보내기 ----------------
st.divider()
review = pd.DataFrame([{"risk_id": k, **v} for k, v in st.session_state.get("review", {}).items()])
with st.container(horizontal=True, gap="small", vertical_alignment="center"):
    st.markdown("**내보내기**")
    st.download_button("브리핑 (Markdown)", to_markdown(report), f"{report.company}_brief.md", icon=":material/article:")
    st.download_button("전체 결과 (JSON)", export_json(report), f"{report.company}_report.json",
                       icon=":material/data_object:")
    st.download_button("감사인 검토 기록 (CSV)", review.to_csv(index=False).encode("utf-8-sig"),
                       f"{report.company}_review.csv", disabled=review.empty, icon=":material/rate_review:")
