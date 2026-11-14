"""scanner — 감사 Risk Scanner의 분석 엔진.

수집(collect) → 정제(clean) → 분석(analyze) → 가드레일(guardrails) → Risk Mapping(risk_map)
→ 재무 신호(finance) · 중요성(materiality) · 특수관계자(related_party) → 리포트(pipeline, brief).
화면(Streamlit)에 의존하지 않으므로 테스트와 스크립트에서 바로 쓸 수 있다.
"""
