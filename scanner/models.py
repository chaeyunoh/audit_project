"""파이프라인 전 단계에서 공유하는 데이터 구조.

설계 원칙: 모든 '주장(Claim)'은 유형(사실/추론/미확인)과 출처 ID를 반드시 가진다.
출처 없는 주장은 가드레일 단계에서 '미확인'으로 강등된다.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .finance import FinancialData, FinancialSignal, LevelCheck
from .materiality import Materiality
from .related_party import RPTReview


class ClaimType(str, Enum):
    FACT = "FACT"              # 회사 공시 등 원자료에 직접 근거한 사실
    INFERENCE = "INFERENCE"    # 산업 특성에서 도출한 추론 (확인 필요)
    UNVERIFIED = "UNVERIFIED"  # 현재 자료로 확인 불가


CLAIM_LABEL = {
    ClaimType.FACT: "Fact",
    ClaimType.INFERENCE: "Industry Inference",
    ClaimType.UNVERIFIED: "Unverified",
}

SourceScope = Literal["company", "industry", "knowledge_base"]


# ---------- 1. 수집 ----------
class SourceDoc(BaseModel):
    """수집 단계의 원천자료 1건."""
    doc_id: str                      # 예: S01
    title: str                       # 예: 가나건설 사업보고서(2025) II. 사업의 내용
    publisher: str                   # 예: DART / 국토교통부 / 사용자 업로드
    published: str = ""              # 공시·발간일
    url: str = ""
    scope: SourceScope = "company"
    raw_text: str


# ---------- 2. 정제 ----------
class Chunk(BaseModel):
    """정제 후 분석 단위. LLM에는 이 단위로만 전달되고, 인용도 이 ID로 한다."""
    chunk_id: str                    # 예: S01-003
    doc_id: str
    scope: SourceScope
    text: str


class CleaningReport(BaseModel):
    masked_items: dict[str, int] = Field(default_factory=dict)  # 마스킹 유형별 건수
    blocked_docs: list[str] = Field(default_factory=list)      # 민감자료로 차단된 문서
    chunk_count: int = 0


# ---------- 3. 분석 ----------
class Claim(BaseModel):
    text: str
    claim_type: ClaimType
    source_ids: list[str] = Field(default_factory=list)
    quote: str = ""  # FACT의 근거 원문 (원문에 글자 그대로 있어야 함)
    flags: list[str] = Field(default_factory=list)  # 가드레일이 부착하는 경고


class TraitEvidence(BaseModel):
    trait_id: str
    rationale: str
    claim_type: ClaimType
    source_ids: list[str] = Field(default_factory=list)
    quote: str = ""
    flags: list[str] = Field(default_factory=list)


class Snapshot(BaseModel):
    industry_key: str
    industry_name: str
    business_model: list[Claim]
    value_chain: list[str]
    stakeholders: list[Claim]
    characteristics: list[Claim]
    information_gaps: list[Claim]


# ---------- 4. Risk Mapping ----------
class AuditQuestion(BaseModel):
    question: str
    origin: Literal["KB", "AI", "FIN", "XCHK"]  # 지식베이스 / AI 생성 / 재무 신호 / 교차점검 템플릿
    purpose: str = ""
    source_ids: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    risk_id: str
    title: str
    trait: str
    potential_risk: str
    accounts: list[str]
    assertions: list[str]
    references: list[str]
    evidence_docs: list[str]
    priority: Literal[1, 2, 3]                  # 1=우선 검토 제안
    basis: Literal["회사 공시로 확인된 특성", "산업 일반 특성", "감사기준상 상시 고려",
                   "재무 지표로 확인된 상황", "감사 유형상 고려"]
    trait_evidence: list[TraitEvidence] = Field(default_factory=list)
    questions: list[AuditQuestion] = Field(default_factory=list)
    fin_signals: list[FinancialSignal] = Field(default_factory=list)


# ---------- 최종 산출물 ----------
class GuardrailEvent(BaseModel):
    stage: str
    action: str
    detail: str


class StepLog(BaseModel):
    step: str
    started: str
    seconds: float
    note: str = ""


class Report(BaseModel):
    company: str
    generated_at: str
    mode: Literal["LLM", "OFFLINE"]
    model: str = ""
    prompt_version: str = ""
    sources: list[SourceDoc]
    chunks: list[Chunk]
    cleaning: CleaningReport
    snapshot: Snapshot
    risks: list[RiskItem]
    guardrail_events: list[GuardrailEvent]
    financials: FinancialData | None = None
    overview_signals: list[FinancialSignal] = Field(default_factory=list)
    going_concern: list[LevelCheck] = Field(default_factory=list)
    rpt: RPTReview | None = None
    materiality: Materiality | None = None              # 적용 중인 값 (화면에서 감사인이 바꾸면 갱신)
    materiality_suggested: Materiality | None = None    # 도구 제안값 (바뀌지 않음 — 감사인 변경과 비교용)
    engagement: Literal["초도감사", "계속감사"] = "계속감사"
    induty_code: str = ""   # DART 기업개황 업종코드(KSIC) — 산업 판별의 근거
    stock_code: str = ""    # 상장 종목코드 (비상장이면 빈 값)
    company_profile: dict = Field(default_factory=dict)       # DART 기업개황 + 보고서 정보
    business_sections: list[dict] = Field(default_factory=list)  # 사업의 내용 표준 소제목별 원문·표·핵심 수치
    warnings: list[str] = Field(default_factory=list)   # 자료 최신성·AI 실패 대체 등
    steps: list[StepLog]
    input_fingerprint: str
