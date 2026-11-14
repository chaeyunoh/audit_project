"""파이프라인 기본 흐름 — 정제·보안 게이트, 가드레일(인용·수치·단정 표현·통제 어휘), 데모 기업 전체 실행."""

from scanner import collect, kb
from scanner.analyze import OfflineAnalyzer
from scanner.clean import clean
from scanner.guardrails import Guard
from scanner.models import AuditQuestion, Chunk, Claim, ClaimType, SourceDoc, TraitEvidence
from scanner.pipeline import run


def _chunks():
    return [Chunk(chunk_id="S01-001", doc_id="S01", scope="company",
                  text="당사는 투입원가 기준 진행률에 따라 공사수익을 인식합니다. 2025년 말 수주잔고는 3조 2,450억원입니다."),
            Chunk(chunk_id="S02-001", doc_id="S02", scope="industry", text="PF 차환 부담이 커지고 있다.")]


# ---------- 정제 · 보안 ----------
def test_sensitive_doc_blocked_and_pii_masked():
    docs = [SourceDoc(doc_id="S01", title="a", publisher="p", raw_text="<p>문의 010-1234-5678, a@b.com 공사</p>"),
            SourceDoc(doc_id="S02", title="b", publisher="p", raw_text="대외비 자료")]
    kept, chunks, rep = clean(docs)
    assert [d.doc_id for d in kept] == ["S01"]
    assert "010-1234-5678" not in chunks[0].text and "a@b.com" not in chunks[0].text
    assert rep.masked_items == {"이메일": 1, "전화번호": 1}


def test_public_filing_is_not_blocked_by_keyword_but_upload_is():
    text = "당사는 영업기밀 보호를 위해 협력사와 비밀유지계약을 체결하고 있습니다."
    docs = [SourceDoc(doc_id="S02", title="사업의 내용", publisher="DART", raw_text=text),
            SourceDoc(doc_id="S09", title="업로드", publisher="사용자 업로드", scope="industry", raw_text=text)]
    kept, _, rep = clean(docs)
    assert [d.doc_id for d in kept] == ["S02"]          # 공시는 출처상 공개 → 통과
    assert rep.blocked_docs and "S09" in rep.blocked_docs[0]


# ---------- 가드레일 ----------
def test_fact_without_company_source_is_downgraded():
    g = Guard(_chunks())
    c = g.claim(Claim(text="PF 차환 부담이 크다", claim_type=ClaimType.FACT, source_ids=["S02-001"]), "t")
    assert c.claim_type == ClaimType.INFERENCE


QUOTE = "2025년 말 수주잔고는 3조 2,450억원입니다."


def test_fact_with_invented_number_is_unverified():
    g = Guard(_chunks())
    c = g.claim(Claim(text="수주잔고는 5조원입니다", claim_type=ClaimType.FACT, source_ids=["S01-001"],
                      quote=QUOTE), "t")
    assert c.claim_type == ClaimType.UNVERIFIED


def test_fact_with_matching_number_kept():
    g = Guard(_chunks())
    c = g.claim(Claim(text="2025년 말 수주잔고는 3조 2,450억원", claim_type=ClaimType.FACT,
                      source_ids=["S01-001"], quote=QUOTE), "t")
    assert c.claim_type == ClaimType.FACT and not c.flags


def test_fact_needs_verbatim_quote():
    g = Guard(_chunks())
    no_quote = g.claim(Claim(text="2025년 말 수주잔고는 3조 2,450억원", claim_type=ClaimType.FACT,
                             source_ids=["S01-001"]), "t")
    assert no_quote.claim_type == ClaimType.INFERENCE            # 인용 없으면 사실 아님
    fake = g.claim(Claim(text="수주잔고 3조 2,450억원", claim_type=ClaimType.FACT, source_ids=["S01-001"],
                         quote="2025년 말 수주잔고는 약 3조 2,450억원 수준이다."), "t")
    assert fake.claim_type == ClaimType.UNVERIFIED               # 원문에 없는 인용
    spaced = g.claim(Claim(text="수주잔고는 3조 2,450억원", claim_type=ClaimType.FACT, source_ids=["S01-001"],
                           quote="2025년 말  수주잔고는\n3조 2,450억원입니다."), "t")
    assert spaced.claim_type == ClaimType.FACT                   # 공백·줄바꿈 차이는 허용


def test_hallucinated_source_removed():
    g = Guard(_chunks())
    c = g.claim(Claim(text="진행률 기준 수익인식", claim_type=ClaimType.INFERENCE, source_ids=["S09-999"]), "t")
    assert c.source_ids == [] and c.claim_type == ClaimType.UNVERIFIED


def test_conclusive_language_flagged_and_question_dropped():
    g = Guard(_chunks())
    c = g.claim(Claim(text="이 회사는 위험하다", claim_type=ClaimType.INFERENCE, source_ids=["S01-001"]), "t")
    assert any("단정" in f for f in c.flags)
    assert g.question(AuditQuestion(question="매출에 오류가 있다는 점을 인정하는가?", origin="AI"), "q") is None


def test_trait_outside_vocabulary_rejected():
    g = Guard(_chunks())
    t = TraitEvidence(trait_id="MADE-UP", rationale="x", claim_type=ClaimType.FACT, source_ids=["S01-001"])
    assert g.trait(t, set(kb.trait_ids("construction")), "t") is None


# ---------- 산업 판별 ----------
def test_ksic_mapping():
    assert kb.industry_from_ksic("41221") == "construction"
    assert kb.industry_from_ksic("26111") == "semiconductor"
    assert kb.industry_from_ksic("99999") is None


# ---------- 전체 파이프라인 (오프라인) ----------
def test_demo_end_to_end():
    demos = collect.list_demos()
    docs, meta = collect.load_demo(demos["가나건설(가상 예시)"])
    r = run(meta["corp_name"], docs, meta, OfflineAnalyzer(), save=False)
    ids = {k.risk_id for k in r.risks}
    assert {"CON-R1", "CON-R5", "G-REV", "G-MO"} <= ids
    assert r.cleaning.blocked_docs                       # 대외비 문서 차단
    assert all(k.questions for k in r.risks)            # 모든 영역에 확인 질문
    pf = next(k for k in r.risks if k.risk_id == "CON-R5")
    assert pf.basis == "회사 공시로 확인된 특성" and pf.priority == 1
    facts = [c for c in r.snapshot.business_model if c.claim_type == ClaimType.FACT]
    assert facts and all(c.source_ids[0].startswith("S01") for c in facts)
