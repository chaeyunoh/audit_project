"""전체 파이프라인: 수집 → 정제 → 분석 → 가드레일 → Risk Mapping → 질문 → 리포트.

각 단계의 입력·출력과 소요시간을 기록해, 결과가 이상할 때 어느 단계에서 생긴
문제인지 역추적할 수 있게 한다 (원천 거래 → 재무제표 추적과 같은 원리).
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from . import finance, kb, ksic, materiality, related_party
from .clean import clean, mask_pii
from .guardrails import Guard
from .finance import FinancialData
from .models import AuditQuestion, Report, SourceDoc, StepLog
from .report_parse import parse_business
from .risk_map import _risk
from .risk_map import map_risks

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"
MAX_AI_QUESTIONS_PER_RISK = 2


class _Timer:
    def __init__(self, steps: list[StepLog], name: str):
        self.steps, self.name, self.note = steps, name, ""

    def __enter__(self):
        self.t0, self.started = time.perf_counter(), datetime.now().isoformat(timespec="seconds")
        return self

    def __exit__(self, *exc):
        self.steps.append(StepLog(step=self.name, started=self.started,
                                  seconds=round(time.perf_counter() - self.t0, 2), note=self.note))


def _biz_text(docs: list[SourceDoc]) -> str:
    return " ".join(d.raw_text for d in docs if d.doc_id in ("S01", "S02")) or " ".join(d.raw_text for d in docs)


def resolve_industry(meta: dict, docs: list[SourceDoc]) -> str:
    """산업 판별. 공식 업종코드(KSIC)가 근거이고, 본문 키워드는 코드가 없을 때만 쓴다.

    업종코드가 있는데 지식베이스에 없는 산업이면 비슷한 산업에 끼워 넣지 않고 'ksic:<코드>'(미지원)로 둔다.
    """
    code = (meta.get("induty_code") or "").strip()
    if code and kb.is_holding(code):
        # 지주회사 코드는 사업을 말해 주지 않는다. 금융지주(은행 표현이 압도적)만 은행 지식베이스를 쓰고,
        # 비금융 지주(SK·CJ·HD한국조선해양 등)는 '지주회사 일반형' 가치사슬로 둔다 — 자회사 산업 적용은 감사인이 직접 지정.
        return "banking" if kb.dominant_industry(_biz_text(docs)) == "banking" else kb.unsupported_key(code)
    if code:
        return kb.industry_from_ksic(code) or kb.unsupported_key(code)
    key = kb.industry_from_text(" ".join(d.raw_text for d in docs))
    if key:
        return key
    raise ValueError("업종코드가 없고 본문만으로 산업을 판단할 근거가 부족합니다. 사이드바에서 산업을 직접 지정하세요. "
                     "현재 지식베이스: " + ", ".join(i["name"] for i in kb.industries().values()))


def run(company: str, docs: list[SourceDoc], meta: dict, analyzer,
        industry_key: str | None = None, save: bool = True,
        financials: FinancialData | None = None, engagement: str = "계속감사") -> Report:
    steps: list[StepLog] = []
    warnings: list[str] = []

    with _Timer(steps, "2. 데이터 정제") as t:
        kept, chunks, cleaning = clean(docs)
        t.note = f"청크 {len(chunks)}개, 차단 {len(cleaning.blocked_docs)}건, 마스킹 {sum(cleaning.masked_items.values())}건"
    if not any(c.scope == "company" for c in chunks):
        raise ValueError("분석 가능한 회사 자료가 없습니다 (모두 차단되었거나 비어 있음).")

    auto_key = resolve_industry(meta, kept)
    code = (meta.get("induty_code") or "").strip()
    if kb.is_holding(code) and not industry_key:
        if kb.is_supported(auto_key):
            warnings.append(f"지주회사 업종코드({code})이지만 사업의 내용이 금융업 중심이라 '{kb.industries()[auto_key]['name']}' "
                            "지식베이스를 적용했습니다. 보험·증권 등 다른 자회사 사업은 다루지 않으니 확인하세요.")
        else:
            dom = kb.dominant_industry(_biz_text(kept))
            warnings.append(f"지주회사 업종코드({code})라 '지주회사 일반형' 가치사슬로 정리했습니다."
                            + (f" 사업의 내용에서는 '{kb.industries()[dom]['name']}' 표현이 압도적이니, 그 산업으로 보려면 "
                               "사이드바 '고급 → 산업 직접 지정'에서 고르세요." if dom else
                               " 자회사 사업이 여러 산업에 걸쳐 있어 특정 산업 지식베이스를 적용하지 않았습니다."))
    if not kb.is_supported(auto_key) and not kb.is_holding(code):
        # 업종코드가 지식베이스 밖이어도, 같은 KSIC 중분류의 산업이 본문에서 압도적으로 확인되면 그 산업을 적용한다.
        # 예) 삼성전자 KSIC 264(통신·방송장비)지만 사업의 내용은 반도체가 주력 → '반도체' 적용, 경고로 근거를 남김.
        rel = kb.related_industry(code)
        biz_text = " ".join(d.raw_text for d in kept if d.doc_id not in set((meta.get("rpt_docs") or {}).values()))
        hits = kb.keyword_hits(rel, biz_text) if rel else 0
        if rel and hits >= kb.SAME_DIVISION_MIN_HITS:
            warnings.append(f"업종코드는 {ksic.label(code)}이지만, 같은 중분류인 '{kb.industries()[rel]['name']}' 관련 표현이 "
                            f"사업의 내용에 {hits}회 나와 이 산업 지식베이스를 적용했습니다. 다른 사업부문은 다루지 않으니 확인하세요.")
            auto_key = rel
    if industry_key and industry_key != auto_key:
        warnings.append(f"산업을 수동으로 '{kb.industry(industry_key)['name']}'(으)로 지정해 분석했습니다 "
                        f"(자동 판별: {kb.industry(auto_key)['name']}). 다른 회사를 분석할 때는 지정을 해제하세요.")
    industry_key = industry_key or auto_key
    review = kb.industry(industry_key).get("review", {})
    if review.get("status") == "draft":
        warnings.append(f"'{kb.industry(industry_key)['name']}' 지식베이스는 초안입니다(감사인 검토 전). "
                        f"산업 특성·검토 영역·질문을 그대로 쓰지 말고 검토하세요. {review.get('note', '')}".strip())
    if not kb.is_supported(industry_key) and not kb.is_holding((meta.get("induty_code") or "").strip()):
        code = (meta.get("induty_code") or "").strip()
        rel = kb.related_industry(code)
        # 같은 중분류라도 사업 내용이 전혀 다를 수 있다 (화장품 20423 ↔ 석유화학 201).
        # 본문에 그 산업의 표현이 어느 정도 나올 때만 '참고하라'고 제안한다.
        biz = " ".join(d.raw_text for d in kept if d.doc_id not in set((meta.get("rpt_docs") or {}).values()))
        if rel and kb.keyword_hits(rel, biz) < kb.RELATED_HINT_MIN_HITS:
            rel = None
        warnings.append(
            f"이 회사의 업종({ksic.label(code)})은 산업 지식베이스에 아직 없습니다. 업종 일반형 가치사슬과 "
            "감사기준상 공통 영역으로 정리했습니다." + (f" 같은 중분류의 '{kb.industries()[rel]['name']}'을(를) 참고하려면 사이드바에서 직접 지정하세요."
                              if rel else ""))
    guard = Guard(chunks)

    # 사업 구조·산업 특성은 '사업의 내용' 등 본문에서만 찾는다. 특수관계자 구간은 교차점검 전용이다.
    # (실제 공시에서 계열사 이름 목록이 '사업 구조 = 사실'로 뽑히는 오류가 있었다)
    rpt_ids = set((meta.get("rpt_docs") or {}).values())
    analysis_chunks = [c for c in chunks if c.doc_id not in rpt_ids]

    with _Timer(steps, "3. 산업 분석") as t:
        snapshot, traits = analyzer.analyze(industry_key, analysis_chunks)
        t.note = f"특성 후보 {len(traits)}개"

    with _Timer(steps, "5. AI 역할 제한(가드레일)") as t:
        allowed = set(kb.trait_ids(industry_key))
        traits = [x for x in (guard.trait(tr, allowed, "특성") for tr in traits) if x]
        snapshot = snapshot.model_copy(update={
            f: [guard.claim(c, f) for c in getattr(snapshot, f)]
            for f in ("business_model", "stakeholders", "characteristics", "information_gaps")})
        t.note = f"이벤트 {len(guard.events)}건"

    with _Timer(steps, "4. 감사 Risk Mapping") as t:
        risks = map_risks(industry_key, traits)
        t.note = f"검토 영역 {len(risks)}개 (지식베이스 v{kb.kb_version()})"

    overview = []
    with _Timer(steps, "4-1. 재무 신호(분석적 절차)") as t:
        # AI를 거치지 않는 결정적 계산. 숫자는 DART 원본, 지표·기준은 지식베이스.
        if financials:
            signals = finance.evaluate(financials, [r.risk_id for r in risks])
            overview = [s for s in signals if s.risk_id is None]
            for r in risks:
                r.fin_signals = [s for s in signals if s.risk_id == r.risk_id]
                r.questions += [AuditQuestion(question=s.question, origin="FIN", source_ids=[financials.source_id],
                                              purpose=f"{s.metric}: {s.formula}")
                                for s in r.fin_signals if s.triggered]
            t.note = f"지표 {len(signals)}개, 확인 신호 {sum(s.triggered for s in signals)}개"
        else:
            t.note = "재무 데이터 없음 — 건너뜀"

    going = []
    with _Timer(steps, "4-2. 계속기업 지표판 · 감사 유형") as t:
        gc = kb.conditional_risk("going_concern")
        if financials:
            going = finance.going_concern_checks(financials, gc["thresholds"])
            flagged = [c for c in going if c.level in ("주의", "위험")]
            if flagged:
                r = _risk(gc["risk"], "; ".join(f"{c.item} {c.level}({c.value})" for c in flagged),
                          1 if any(c.level == "위험" for c in flagged) else 2, "재무 지표로 확인된 상황", [])
                risks.insert(0, r)
            t.note = f"주의·위험 {len(flagged)}건, 확인 필요 {sum(c.level == '확인 필요' for c in going)}건"
        if engagement == "초도감사":
            ob = kb.conditional_risk("first_year")["risk"]
            risks.insert(0, _risk(ob, ob["trait"], ob["priority"], "감사 유형상 고려", []))
        risks.sort(key=lambda x: x.priority)

    rpt = None
    with _Timer(steps, "4-3. 특수관계자 교차점검") as t:
        ids = meta.get("rpt_docs") or {}
        texts = {d.doc_id: d.raw_text for d in kept}
        recorded = meta.get("rpt_recorded") or {}

        def extraction(label: str, sid: str | None):
            text = texts.get(sid) if sid else None
            if not text:
                return related_party.build_extraction(label, sid, None, None, "-")
            if sid in recorded:  # 데모: 미리 기록한 추출 응답도 같은 인용 검증을 거친다
                return related_party.build_extraction(label, sid, text, recorded[sid], "데모 고정 응답")
            return related_party.build_extraction(label, sid, text, None, "-")

        cut = meta.get("rpt_truncated") or {}
        biz = extraction("사업보고서 '대주주 등과의 거래'", ids.get("business"))
        notes = extraction("재무제표 주석 '특수관계자'", ids.get("notes"))
        # 잘림 여부는 추출 결과와 무관하게 원문 수집 단계의 사실이므로 여기서 붙인다
        biz.truncated, notes.truncated = bool(cut.get("business")), bool(cut.get("notes"))
        rpt = related_party.cross_check(biz, notes, related_party.table_unit(texts.get(ids.get("business"), "")),
                                        related_party.table_unit(texts.get(ids.get("notes"), "")))
        for ex in (biz, notes):
            for d in ex.dropped:
                guard._log("특수관계자", f"추출 항목 제외({d['reason']})", d["detail"])
        g_rp = next((r for r in risks if r.risk_id == "G-RP"), None)
        if g_rp:
            g_rp.questions += [AuditQuestion(question=q, origin="XCHK", source_ids=[x for x in (biz.source_id, notes.source_id) if x])
                               for q in related_party.questions(rpt)]
        t.note = f"불일치 {len(rpt.discrepancies)}건 / {biz.status}·{notes.status}"

    # 계획 중요성: 도구의 제안값으로 시작하고, 화면에서 감사인이 바꾼다
    mat = None
    if financials:
        higher_risk = engagement == "초도감사" or any(c.level in ("주의", "위험") for c in going)
        mat = materiality.default(financials, higher_risk)

    # 자료 최신성 (기준연도)
    if financials:
        latest, ry = financials.years[-1], meta.get("report_year")
        if latest < datetime.now().year - 1:
            warnings.append(f"재무자료 최신 연도가 {latest}년입니다. 이후 공시(반기·분기보고서)를 별도로 확인하세요.")
        if ry and ry != latest:
            warnings.append(f"사업보고서 기준연도({ry})와 재무자료 기준연도({latest})가 다릅니다.")

    with _Timer(steps, "6. 확인 질문 생성") as t:
        industry_risks = [r for r in risks if r.basis in ("회사 공시로 확인된 특성", "산업 일반 특성")]
        added = 0
        per_risk: dict[str, int] = {}
        for rid, q in analyzer.questions(industry_risks, analysis_chunks):
            q = guard.question(q, "질문")
            if not q or per_risk.get(rid, 0) >= MAX_AI_QUESTIONS_PER_RISK:
                continue
            for r in risks:
                if r.risk_id == rid:
                    r.questions.append(q)
                    per_risk[rid] = per_risk.get(rid, 0) + 1
                    added += 1
        t.note = f"AI 질문 {added}개 추가"

    fingerprint = hashlib.sha256("".join(c.text for c in chunks).encode()).hexdigest()[:16]
    report = Report(
        company=company, generated_at=datetime.now().isoformat(timespec="seconds"),
        mode=analyzer.mode, model=getattr(analyzer, "model", ""),
        sources=kept, chunks=chunks, cleaning=cleaning, snapshot=snapshot, risks=risks,
        guardrail_events=guard.events, steps=steps, input_fingerprint=fingerprint,
        financials=financials, overview_signals=overview, going_concern=going, rpt=rpt,
        engagement=engagement, warnings=warnings, materiality=mat, materiality_suggested=mat,
        induty_code=(meta.get("induty_code") or "").strip(), stock_code=meta.get("stock_code", "") or "",
        company_profile=meta.get("company_profile") or {},
        business_sections=_mask_sections(meta.get("business_sections") or _sections_from_docs(kept)),
    )
    if save:
        RUNS_DIR.mkdir(exist_ok=True)
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{fingerprint}.json"
        (RUNS_DIR / name).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def _mask_sections(sections: list[dict]) -> list[dict]:
    """구조화한 사업의 내용에도 정제 단계와 같은 개인정보 마스킹을 적용한다 (표 칸 포함).
    같은 원문이 정제 단계에서 이미 집계되므로 건수는 다시 세지 않는다."""
    m = lambda t: mask_pii(t, {})
    return [{**s, "text": m(s["text"]), "lead": [m(x) for x in s["lead"]], "facts": [m(x) for x in s["facts"]],
             "tables": [{**t, "rows": [[m(c) for c in r] for r in t["rows"]]} for t in s["tables"]]}
            for s in sections]


def _sections_from_docs(docs: list[SourceDoc]) -> list[dict]:
    """DART 외 입력(데모 등): '사업' 제목의 회사 문서를 같은 방식으로 구조화한다. 정제(마스킹)된 원문을 쓴다."""
    doc = next((d for d in docs if d.scope == "company" and "사업" in d.title), None)
    return parse_business(doc.raw_text) if doc else []


def source_label(report: Report, source_id: str) -> str:
    if report.financials and source_id == report.financials.source_id:
        f = report.financials
        return f"{f.publisher} · {f.title} ({f.basis}, 단위 {f.unit})"
    if source_id == "KB":
        return f"산업 지식베이스 v{kb.kb_version()} (작성자 검토)"
    doc_id = source_id.split("-")[0]
    for d in report.sources:
        if d.doc_id == doc_id:
            date = f" / {d.published}" if d.published else ""
            return f"{d.publisher} · {d.title}{date}"
    return source_id


def export_json(report: Report) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
