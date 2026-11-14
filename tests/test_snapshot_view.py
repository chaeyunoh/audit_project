"""산업 스냅샷 화면 데이터 — 모든 특성이 가치사슬 단계에 놓이고, 확인 상태 순서가 일관된지 검사한다."""

from scanner import collect, kb
from scanner.analyze import OfflineAnalyzer
from scanner.models import ClaimType
from scanner.pipeline import run
from snapshot_view import trait_views


def test_every_trait_stage_is_on_its_value_chain():
    for key, ind in kb.industries().items():
        chain = ind["profile"]["value_chain"]
        for t in ind["traits"]:
            assert t.get("stage") in chain, f"{key}/{t['trait_id']} stage '{t.get('stage')}' not in value_chain"


def test_trait_views_cover_all_kb_traits_with_consistent_status():
    demos = collect.list_demos()
    docs, meta = collect.load_demo(next(iter(demos.values())))
    r = run("demo", docs, meta, OfflineAnalyzer(), save=False, financials=meta.get("financials"))
    views = trait_views(r)

    assert {v.trait_id for v in views} == set(kb.trait_ids(r.snapshot.industry_key))
    for v in views:
        if v.status == ClaimType.UNVERIFIED:
            assert not v.evidence and not v.risks
        else:
            assert v.evidence and v.risks
            # 한 특성에 위험이 여럿이어도 근거는 중복되지 않는다
            keys = [(e.rationale, tuple(e.source_ids)) for e in v.evidence]
            assert len(keys) == len(set(keys))
    # 공시 확인 → 추론 → 미확인 순으로 정렬
    order = [list(ClaimType).index(v.status) for v in views]
    assert order == sorted(order)
