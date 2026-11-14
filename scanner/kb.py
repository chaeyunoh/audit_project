"""산업 지식베이스(industry_kb.yaml) 로더."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "industry_kb.yaml"


@lru_cache(maxsize=1)
def load_kb() -> dict:
    with open(KB_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def industries() -> dict[str, dict]:
    return load_kb()["industries"]


def industry_from_ksic(induty_code: str) -> str | None:
    """DART 기업개황의 업종코드(KSIC)로 산업 키를 찾는다. 가장 긴 접두어 우선."""
    best, best_len = None, 0
    for key, ind in industries().items():
        for p in ind["ksic_prefixes"]:
            if induty_code.startswith(p) and len(p) > best_len:
                best, best_len = key, len(p)
    return best


TEXT_MIN_HITS = 5  # 본문 키워드 판별은 이 정도 근거가 있을 때만 (우연한 단어 몇 개로 산업을 정하지 않음)


def industry_from_text(text: str, min_hits: int = TEXT_MIN_HITS) -> str | None:
    """업종코드가 없거나(또는 지주회사처럼 코드가 사업을 말해 주지 않을 때) 쓰는 보조 판별: 산업 키워드 출현 빈도.
    근거가 약하면 None."""
    scores = {k: sum(text.count(w) for w in ind["detect_keywords"]) for k, ind in industries().items()}
    key, score = max(scores.items(), key=lambda kv: kv[1])
    return key if score >= min_hits else None


HOLDING_CODES = ("64992",)   # 지주회사: 금융지주와 비금융 지주(SK·HD한국조선해양 등)가 같은 코드


def is_holding(induty_code: str) -> bool:
    return (induty_code or "").startswith(HOLDING_CODES)


def dominant_industry(text: str, min_hits: int = 30, ratio: float = 2.0) -> str | None:
    """본문에서 한 산업이 압도적일 때만(최다 ≥ min_hits, 2위의 ratio배 이상) 그 산업. 복합 기업이면 None."""
    sc = sorted(((sum(text.count(w) for w in ind["detect_keywords"]), k) for k, ind in industries().items()), reverse=True)
    if not sc or sc[0][0] < min_hits:
        return None
    return sc[0][1] if len(sc) == 1 or sc[0][0] >= ratio * max(sc[1][0], 1) else None


# ---------------- 지식베이스에 없는 산업 ----------------
# 업종코드는 있지만 지식베이스가 다루지 않는 산업은 억지로 비슷한 산업에 끼워 넣지 않는다.
# 'ksic:<코드>' 키로 표시하고, 산업 특성 없이 감사기준상 공통 영역만 연결한다.
UNSUPPORTED_PREFIX = "ksic:"
GENERIC_KEYWORDS = ["주요 제품", "주요 사업", "매출", "고객", "원재료", "생산", "서비스", "판매"]


def is_supported(industry_key: str) -> bool:
    return industry_key in industries()


def unsupported_key(induty_code: str) -> str:
    return f"{UNSUPPORTED_PREFIX}{induty_code or 'unknown'}"


def generic_chains() -> list[dict]:
    return load_kb().get("generic_value_chains", [])


def _in_divisions(div: int, spans: list) -> bool:
    for x in spans:
        lo, _, hi = str(x).partition("-")
        if int(lo) <= div <= int(hi or lo):
            return True
    return False


def generic_chain(induty_code: str) -> dict | None:
    """KSIC 중분류(앞 2자리)로 업종 일반 가치사슬 템플릿을 고른다. 맞는 게 없으면 서비스업 일반형, 코드가 없으면 None."""
    code = (induty_code or "").strip()
    if len(code) < 2 or not code[:2].isdigit():
        return None
    div = int(code[:2])
    chains = generic_chains()
    hit = next((c for c in chains if any(code.startswith(p) for p in c.get("ksic_prefixes", []))), None)         or next((c for c in chains if _in_divisions(div, c["ksic_divisions"])), None)
    return hit or next((c for c in chains if c["key"] == "services"), None)


def industry(industry_key: str) -> dict:
    """지식베이스 산업, 또는 미지원 산업 프로필(산업 특성 없음 + 업종 일반 가치사슬 템플릿)."""
    if industry_key in industries():
        return industries()[industry_key]
    from .ksic import division_name
    code = industry_key.removeprefix(UNSUPPORTED_PREFIX)
    name = division_name(code) or "업종 미확인"
    tpl = generic_chain(code)
    return {"name": name, "supported": False, "ksic": code, "ksic_prefixes": [],
            "detect_keywords": GENERIC_KEYWORDS, "summary": "", "template": tpl["name"] if tpl else "",
            "profile": {"business_model": [], "value_chain": list(tpl["value_chain"]) if tpl else [],
                        "stakeholders": [], "stage_info": dict(tpl["stage_info"]) if tpl else {}},
            "traits": []}


def related_industry(induty_code: str) -> str | None:
    """미지원 업종과 같은 KSIC 중분류(2자리)를 쓰는 지식베이스 산업 — '참고로 볼 만한 산업' 제안용."""
    div = (induty_code or "")[:2]
    for key, ind in industries().items():
        if any(p[:2] == div for p in ind["ksic_prefixes"]):
            return key
    return None


SAME_DIVISION_MIN_HITS = 30  # 업종코드가 밖일 때 같은 중분류 산업을 적용하려면 본문에서 이만큼 확인돼야 함
RELATED_HINT_MIN_HITS = 5    # 적용까지는 아니어도 '참고하라'고 제안하려면 최소 이만큼은 나와야 함


def keyword_hits(industry_key: str, text: str) -> int:
    return sum(text.count(w) for w in industries()[industry_key]["detect_keywords"])


def traits(industry_key: str) -> list[dict]:
    return industry(industry_key)["traits"]


def trait_ids(industry_key: str) -> list[str]:
    return [t["trait_id"] for t in traits(industry_key)]


def baseline_risks() -> list[dict]:
    return load_kb()["baseline_risks"]


def metric_definitions() -> dict[str, list[dict]]:
    """risk_id → 재무 지표 정의 목록 (산업별 위험 + 상시 고려 위험)."""
    risks = [r for ind in industries().values() for t in ind["traits"] for r in t["risks"]]
    risks += baseline_risks()
    return {r["risk_id"]: r["metrics"] for r in risks if r.get("metrics")}


def kb_version() -> str:
    return load_kb()["kb_version"]


def conditional_risk(name: str) -> dict:
    return load_kb()["conditional_risks"][name]
