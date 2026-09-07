"""연봉 정보를 붙인다.

공고 대부분이 "면접 후 결정 / 회사 내규"라 회사별 실제 금액을 알 수 없다.
그렇다고 비워두면 판단이 안 되므로, **업계 참고 범위**를 따로 표시한다.
회사 값인 척하지 않는 것이 핵심이다 — 화면에도 출처를 명시한다.
"""
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
_TABLE: Optional[dict] = None

# 공고에 금액이 없다는 뜻의 상투어들 — 이게 적혀 있으면 '명시 없음'으로 본다
VAGUE = ("면접 후", "회사 내규", "내규에", "협의", "추후", "당社規定", "当社規定",
         "マイページ", "면접후", "상담", "규정에 따름", "依公司規定", "面議")


def table() -> dict:
    global _TABLE
    if _TABLE is None:
        _TABLE = yaml.safe_load(
            (ROOT / "data" / "salary_benchmarks.yaml").read_text(encoding="utf-8"))
    return _TABLE


def stated(posting) -> Optional[str]:
    """공고에 실제 금액이 적혀 있으면 그것. 상투어면 None."""
    s = (posting.salary or "").strip()
    if not s:
        return None
    if any(v in s for v in VAGUE) and not any(ch.isdigit() for ch in s):
        return None
    return s


def benchmark(country: str, tier: Optional[str]) -> Optional[dict[str, Any]]:
    """(국가, 사무소 성격) → 신입 참고 범위. 모르면 None."""
    t = table().get(country)
    if not t:
        return None
    key = tier if tier in t["tiers"] else "mid"
    row = t["tiers"].get(key)
    if not row:
        return None
    lo, hi = row["newgrad"]
    return {
        "range": f"{lo:,}~{hi:,} {t['unit']}",
        "low": lo, "high": hi, "unit": t["unit"], "currency": t["currency"],
        "tier": key, "note": row.get("note"),
        "disclaimer": table()["meta"]["disclaimer"],
    }


def describe(posting, country: str, tier: Optional[str]) -> dict[str, Any]:
    """화면에 그대로 쓸 수 있는 형태로."""
    return {"stated": stated(posting), "benchmark": benchmark(country, tier)}
