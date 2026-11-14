"""7단계 — 검증.

(A) 자동 지표: 매 실행마다 리포트에서 계산 (근거성·환각 통제의 대리 지표)
(B) 사람 평가: 기존 방식(직접 조사) vs MVP 결과를 같은 루브릭으로 채점해 CSV에 누적
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import ClaimType, Report

EVAL_PATH = Path(__file__).resolve().parent.parent / "eval" / "results.csv"

RUBRIC = {
    "Completeness": "주요 산업 특성을 빠뜨리지 않았는가?",
    "Relevance": "감사와 관련된 위험을 제대로 찾아냈는가?",
    "Evidence": "각각의 주장에 근거가 있는가?",
    "Accuracy": "원자료와 일치하는가?",
    "Actionability": "감사인이 다음에 확인할 질문·자료를 얻을 수 있는가?",
    "Hallucination": "근거 없는 위험을 만들어내지 않았는가? (5=전혀 없음)",
}


def auto_metrics(r: Report) -> dict[str, float | int]:
    claims = [c for f in ("business_model", "stakeholders", "characteristics")
              for c in getattr(r.snapshot, f)]
    n = len(claims) or 1
    facts = [c for c in claims if c.claim_type == ClaimType.FACT]
    questions = [q for risk in r.risks for q in risk.questions]
    ai_q = [q for q in questions if q.origin == "AI"]
    return {
        "주장 수": len(claims),
        "출처 부착률(%)": round(100 * sum(1 for c in claims if c.source_ids) / n, 1),
        "사실(FACT) 비율(%)": round(100 * len(facts) / n, 1),
        "경고 없는 사실 비율(%)": round(100 * sum(1 for c in facts if not c.flags) / (len(facts) or 1), 1),
        "가드레일 강등 건수": sum(1 for e in r.guardrail_events if "강등" in e.action),
        "단정 표현 탐지 건수": sum(1 for e in r.guardrail_events if "단정" in e.action),
        "존재하지 않는 출처 인용": sum(1 for e in r.guardrail_events if "존재하지 않는 출처" in e.action),
        "검토 영역 수": len(r.risks),
        "확인 질문 수(KB/AI)": f"{len(questions) - len(ai_q)}/{len(ai_q)}",
        "FACT 인용문 부착률(%)": round(100 * sum(1 for c in facts if c.quote) / (len(facts) or 1), 1),
        "특수관계자 추출 제외(원문 대조 실패)": 0 if not r.rpt else len(r.rpt.business.dropped) + len(r.rpt.notes.dropped),
        "특수관계자 교차점검 불일치": "확인 필요" if not r.rpt or not {r.rpt.business.status, r.rpt.notes.status} <= {"ok", "partial"}
        else len(r.rpt.discrepancies),
        "계속기업 지표 주의·위험": sum(c.level in ("주의", "위험") for c in r.going_concern),
        "재무 확인 신호 수": sum(s.triggered for s in r.overview_signals)
        + sum(s.triggered for k in r.risks for s in k.fin_signals),
        "AI 질문 근거 부착률(%)": round(100 * sum(1 for q in ai_q if q.source_ids) / (len(ai_q) or 1), 1),
    }


def save_human_eval(company: str, method: str, evaluator: str, minutes: float,
                    scores: dict[str, int], missed: str, false_risks: str, note: str) -> None:
    EVAL_PATH.parent.mkdir(exist_ok=True)
    new = not EVAL_PATH.exists()
    with open(EVAL_PATH, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["일시", "회사", "방식", "평가자", "소요시간(분)", *RUBRIC.keys(),
                        "누락된 특성", "근거 없는 위험", "메모"])
        w.writerow([datetime.now().isoformat(timespec="minutes"), company, method, evaluator, minutes,
                    *[scores[k] for k in RUBRIC], missed, false_risks, note])


def load_human_eval() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    with open(EVAL_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
