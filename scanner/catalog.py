"""산업 카탈로그 — 지식베이스만으로 산업을 설명·비교하는 데이터.

회사 자료와 AI를 쓰지 않는다. 화면(산업 둘러보기·깊이 보기·비교)은 이 모듈의 결과만 그린다.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

from . import kb
from .finance import _formula

SECTOR_MAP_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "sector_map.yaml"

SIGNAL_TEXT = {  # 지표 유형 → 확인 신호 기준 문구
    "ratio": "전년 대비 {sign}{t:g}%p 이상 변동",
    "days": "전년 대비 {sign}{t:g}일 이상 변동",
    "growth_gap": "증가율 격차 {t:g}%p 이상",
}
SIGN = {"up": "+", "down": "−", "both": "±"}


def assertions() -> dict[str, str]:
    return kb.load_kb()["assertion_glossary"]


def risk_rows(key: str) -> list[dict]:
    """산업의 (특성, 검토 영역) 쌍을 평평하게 편다."""
    return [{"trait": t, "risk": r} for t in kb.traits(key) for r in t["risks"]]


def metric_rows(key: str) -> list[dict]:
    out = []
    for x in risk_rows(key):
        for m in x["risk"].get("metrics", []):
            sig = m.get("signal", {})
            out.append({
                "지표": m["name"], "산식": _formula(m),
                "확인 신호 기준": SIGNAL_TEXT[m["kind"]].format(sign=SIGN[sig.get("direction", "both")],
                                                            t=sig.get("threshold", 0)) if sig else "-",
                "검토 영역": x["risk"]["title"], "산업 특성": x["trait"]["name"],
            })
    return out


def profile(key: str) -> dict:
    ind = kb.industry(key)
    rows = risk_rows(key)
    return {
        "key": key, "name": ind["name"], "summary": ind.get("summary", ""),
        "review": ind.get("review", {"status": "reviewed"}),
        "business_model": ind["profile"]["business_model"],
        "value_chain": ind["profile"]["value_chain"],
        "stage_info": ind["profile"].get("stage_info", {}),
        "stakeholders": ind["profile"]["stakeholders"],
        "traits": ind["traits"],
        "risks": [x["risk"] for x in rows],
        "top_risks": [x["risk"] for x in rows if x["risk"]["priority"] == 1],
        "accounts": list(dict.fromkeys(a for x in rows for a in x["risk"]["accounts"])),
        "assertions": Counter(a for x in rows for a in x["risk"]["assertions"]),
        "metrics": metric_rows(key),
    }


def account_assertion_rows(key: str) -> list[dict]:
    """산업 안에서 계정 × 경영진 주장 — 어떤 계정의 어떤 주장을 보게 되는지."""
    return [{"계정": a, "경영진 주장": s, "검토 영역": x["risk"]["title"], "우선순위": x["risk"]["priority"]}
            for x in risk_rows(key) for a in x["risk"]["accounts"] for s in x["risk"]["assertions"]]


def assertion_matrix(keys: list[str]) -> list[dict]:
    """산업 × 경영진 주장 — 각 주장이 걸린 검토 영역 수. 산업 간 감사 초점 차이를 보여준다."""
    out = []
    for k in keys:
        c = profile(k)["assertions"]
        out += [{"산업": kb.industries()[k]["name"], "경영진 주장": a, "검토 영역 수": c.get(a, 0)}
                for a in assertions()]
    return out


def shared_references(keys: list[str]) -> list[dict]:
    """기준서·감사기준서별로 어느 산업의 검토 영역에서 쓰이는지 (공통점 파악용)."""
    seen: dict[str, dict[str, list[str]]] = {}
    for k in keys:
        name = kb.industries()[k]["name"]
        for x in risk_rows(k):
            for ref in x["risk"]["references"]:
                seen.setdefault(ref, {}).setdefault(name, []).append(x["risk"]["title"])
    rows = [{"기준": ref, "산업 수": len(by), **{n: ", ".join(t) for n, t in by.items()}}
            for ref, by in seen.items()]
    return sorted(rows, key=lambda r: (-r["산업 수"], r["기준"]))


# ---------------------------------------------------------------- 본부(조직) 체계
@lru_cache(maxsize=1)
def sector_map() -> dict:
    with open(SECTOR_MAP_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def systems() -> list[dict]:
    return sector_map()["systems"]


def system(key: str) -> dict:
    return next(s for s in systems() if s["key"] == key)


def coverage(division: dict) -> tuple[int, int]:
    """(지식베이스로 준비된 섹터 수, 전체 섹터 수). 기능 본부는 (0, 0)."""
    secs = division.get("sectors", [])
    return sum(1 for s in secs if s.get("kb")), len(secs)


def divisions_of(industry_key: str) -> list[dict]:
    """한 산업이 속한 본부들 — 산업 깊이 보기에서 '이 산업을 맡는 본부' 표시용."""
    return [{"체계": s["name"], "본부": d["code"], "이름": d["name"], "섹터": sec["name"]}
            for s in systems() for d in s["divisions"]
            for sec in d.get("sectors", []) if sec.get("kb") == industry_key]


def focus_risks(division: dict) -> list[dict]:
    """기능 본부가 주로 보는 산업 공통 검토 영역."""
    base = {r["risk_id"]: r for r in kb.baseline_risks()}
    return [base[i] for i in division.get("focus", []) if i in base]


def sectors_for_ksic(induty_code: str) -> list[dict]:
    """회사 업종코드(KSIC) → 체계별 본부·섹터. 체계마다 가장 긴 접두어로 맞는 섹터(동률이면 모두)."""
    code = (induty_code or "").strip()
    out = []
    if not code:
        return out
    for s in systems():
        hits = [(len(p), d, sec) for d in s["divisions"] for sec in d.get("sectors", [])
                for p in sec.get("ksic", []) if code.startswith(p)]
        if not hits:
            continue
        best = max(h[0] for h in hits)
        seen = set()
        for n, d, sec in hits:
            if n == best and (d["code"], sec["name"]) not in seen:
                seen.add((d["code"], sec["name"]))
                out.append({"체계": s["name"], "본부": d["code"], "본부명": d["name"], "섹터": sec["name"],
                            "kb": sec.get("kb")})
    return out
