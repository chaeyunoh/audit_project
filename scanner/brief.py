"""감사인용 브리핑(Markdown) 내보내기."""
from __future__ import annotations

from . import kb
from .models import CLAIM_LABEL, Claim, Report
from .pipeline import source_label

PRIORITY_ICON = {1: "🔴", 2: "🟠", 3: "🟡"}


def _claim_line(r: Report, c: Claim) -> str:
    src = "; ".join(f"`{s}`" for s in c.source_ids) or "출처 없음"
    flags = "".join(f"\n  - ⚠️ {f}" for f in c.flags)
    return f"- **[{CLAIM_LABEL[c.claim_type]}]** {c.text} — {src}{flags}"


def to_markdown(r: Report) -> str:
    s = r.snapshot
    out = [
        f"# {r.company} — 산업 이해 기반 감사 브리핑",
        f"> 생성 {r.generated_at} · 모드 {r.mode} {r.model} · 지식베이스 v{kb.kb_version()} · 입력지문 `{r.input_fingerprint}`",
        "> 이 문서는 감사인의 산업 이해와 절차 설계를 돕는 **보조 자료**이며, 위험평가·감사의견 등 "
        "최종 판단은 감사인의 전문가적 판단으로 수행한다.",
        f"> 감사 유형: {r.engagement}",
        *[f"> ⚠️ {w}" for w in r.warnings],
        f"\n## ① Industry Snapshot — {s.industry_name}",
        "### Business Model", *[_claim_line(r, c) for c in s.business_model],
        "### Value Chain", " → ".join(s.value_chain),
        "### 주요 이해관계자", *[_claim_line(r, c) for c in s.stakeholders],
        "### 산업·사업 특성", *[_claim_line(r, c) for c in s.characteristics],
        "\n## ② Industry Risk Map (검토 우선순위 제안)",
        "| 순위 | 검토 영역 | 산업 특성 | 잠재적 위험(확인 필요성) | 관련 계정 | 경영진 주장 | 근거 |",
        "|---|---|---|---|---|---|---|",
    ]
    for k in r.risks:
        out.append(f"| {PRIORITY_ICON[k.priority]} | {k.title} | {k.trait} | {k.potential_risk} | "
                   f"{', '.join(k.accounts)} | {', '.join(k.assertions)} | {k.basis} |")
    out.append("\n## ③ Audit Questions")
    for k in r.risks:
        out.append(f"### {PRIORITY_ICON[k.priority]} {k.title}")
        for i, q in enumerate(k.questions, 1):
            tag = {"AI": "AI 제안", "FIN": "재무 신호"}.get(q.origin, "KB")
            src = f" — {', '.join(q.source_ids)}" if q.source_ids else ""
            out.append(f"{i}. [{tag}] {q.question}{src}")
        out.append(f"- 추가 확인 자료: {', '.join(k.evidence_docs)}")
        out.append(f"- 참고 기준: {', '.join(k.references)}")
    if r.financials:
        f = r.financials
        out += [f"\n## ⑤ Financial Signals ({f.basis}, 단위 {f.unit}, 출처 `{f.source_id}`)",
                "> 숫자는 공시 원본에서 코드로 계산했으며 AI를 거치지 않았다. 확인 신호는 결론이 아니라 확인할 곳이다.",
                "| 위험 영역 | 지표 | " + " | ".join(map(str, f.years)) + " | 전년 대비 | 기준 | 상태 |",
                "|---|---|" + "---|" * len(f.years) + "---|---|---|"]
        titles = {k.risk_id: k.title for k in r.risks}
        for x in r.overview_signals + [x for k in r.risks for x in k.fin_signals]:
            vals = " | ".join("N/A" if x.values.get(y) is None else f"{x.values[y]:,.1f}{x.unit}" for y in f.years)
            chg = "" if x.change is None else f"{x.change:+,.1f}"
            state = "📈 확인 신호" if x.triggered else (x.note or "-")
            out.append(f"| {titles.get(x.risk_id, '개요')} | {x.metric} | {vals} | {chg} | "
                       f"{'' if x.threshold is None else f'{x.threshold:g}'} | {state} |")
        out += [f"- {x.question}" for x in r.overview_signals if x.question]
    m, sug = r.materiality, r.materiality_suggested
    if m and m.ok:
        from .materiality import discrepancy_levels, signal_levels, won_to_unit
        out += ["\n### 계획 중요성 (감사기준서 320)",
                f"- 기준: {m.benchmark_name} {m.year}년 {m.base:,.1f}{m.unit} × {m.pct:g}% → "
                f"계획 중요성 {m.overall:,.1f} · 수행 중요성 {m.performance:,.1f} ({m.perf_pct:g}%) · "
                f"명백히 사소한 금액 {m.trivial:,.1f} ({m.trivial_pct:g}%) {m.unit}",
                f"- 도구 제안 근거: {m.suggestion}"]
        if sug and (m.benchmark, m.pct, m.perf_pct, m.trivial_pct) != (sug.benchmark, sug.pct, sug.perf_pct, sug.trivial_pct):
            out.append(f"- **감사인이 제안값을 변경함** (제안: {sug.benchmark_name} {sug.pct:g}%, 수행 {sug.perf_pct:g}%, "
                       f"사소 {sug.trivial_pct:g}%)")
        lv = signal_levels(r, m)
        hits = [(x, lv[id(x)]) for x in r.overview_signals + [x for k in r.risks for x in k.fin_signals]
                if x.triggered and x.amount_change is not None]
        out += [f"- {x.metric}: {x.amount_account} 기대치 {x.expected:,.0f} 대비 {x.amount_change:+,.0f}{m.unit} → {lvl}"
                for x, lvl in hits]
        if r.rpt:
            dl = discrepancy_levels(r, m)
            out += [f"- 특수관계자 불일치 차이 {won_to_unit(d.gap_won, m.unit):,.1f}{m.unit} → {dl[id(d)]} ({d.issue})"
                    for d in r.rpt.discrepancies if d.gap_won is not None]
    if r.going_concern:
        out += ["\n### 계속기업 지표판 (감사기준서 570)", "| 항목 | 수준 | 값 | 근거 |", "|---|---|---|---|"]
        out += [f"| {c.item} | {c.level} | {c.value} | {c.reason} |" for c in r.going_concern]
    if r.rpt:
        from .related_party import STATUS_LABEL
        out += ["\n## ⑥ 특수관계자 교차점검 (감사기준서 550)",
                f"- {r.rpt.business.label}: {STATUS_LABEL[r.rpt.business.status]} "
                f"(대조 통과 {len(r.rpt.business.items)}건, 제외 {len(r.rpt.business.dropped)}건, {r.rpt.business.origin})",
                f"- {r.rpt.notes.label}: {STATUS_LABEL[r.rpt.notes.status]} "
                f"(대조 통과 {len(r.rpt.notes.items)}건, 제외 {len(r.rpt.notes.dropped)}건, {r.rpt.notes.origin})"]
        out += [f"- ⚠️ {d.issue} — {d.evidence}" for d in r.rpt.discrepancies] or ["- 비교한 항목 사이 불일치 없음"]
    out += ["\n## ④ Evidence", "### 출처 목록"]
    out += [f"- `{d.doc_id}` {source_label(r, d.doc_id)} {d.url}" for d in r.sources]
    if r.financials:
        out.append(f"- `{r.financials.source_id}` {source_label(r, r.financials.source_id)} {r.financials.url}")
    out += ["### 확인되지 않은 사항 (Unverified)", *[f"- {c.text}" for c in s.information_gaps]]
    events = [f"- [{e.stage}] {e.action}: {e.detail}" for e in r.guardrail_events]
    out += ["### AI 통제 로그", *(events or ["- 이벤트 없음"])]
    return "\n".join(out)
