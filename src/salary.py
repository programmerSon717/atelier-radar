"""연봉 정보를 붙인다.

사용자 지시: **업계 평균은 적지 마라.** 그건 그 회사 이야기가 아니라서 판단에 도움이
안 된다. 대신 두 가지만 싣는다.

  1) 공고에 실제로 적힌 금액
  2) 그 회사에 대해 실제로 돌아다니는 이야기 (블라인드·잡플래닛·OpenWork·104 등).
     정확한 값이 아니므로 **[카더라]** 라고 붙여서, 확인된 값과 절대 섞이지 않게 한다.

2번은 사람이 확인해 data/verified/salary.yaml 에 적어 넣는다. 자동으로 긁지 않는다 —
블라인드는 로그인이 필요하고, 로그인 뒤 내용을 긁는 건 하지 않기로 했다.
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


RUMOR_PATH = ROOT / "data" / "salary_company.yaml"
_RUMOR: Optional[dict] = None


def rumors() -> dict:
    """회사별 연봉. tools/fetch_company_salary.py 가 사람인에서 받아 채운다."""
    global _RUMOR
    if _RUMOR is None:
        if RUMOR_PATH.exists():
            _RUMOR = yaml.safe_load(RUMOR_PATH.read_text(encoding="utf-8")) or {}
        else:
            _RUMOR = {}
    return _RUMOR


def _norm(x: str) -> str:
    import re
    return re.sub(r"[\s·,.\-_()（）]|주식회사|㈜|\(주\)|株式会社|有限公司", "", (x or "")).lower()


def rumor(company: Optional[str], office_id: Optional[str]) -> Optional[dict[str, Any]]:
    """이 회사 값이 있으면 돌려준다. 없으면 None. 업계 평균은 쓰지 않는다."""
    tbl = rumors().get("companies") or {}
    n = _norm(company)
    if not n:
        return None
    for k, v in tbl.items():
        for alias in [k, v.get("company", "")]:
            a = _norm(alias)
            if a and (a == n or a in n or n in a):
                return {**v, "key": k}
    return None


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


def describe(posting, country: str, tier: Optional[str],
             office_id: Optional[str] = None) -> dict[str, Any]:
    """화면에 그대로 쓸 수 있는 형태로. 업계 평균은 넣지 않는다."""
    return {
        "stated": stated(posting),
        "company_avg": rumor(getattr(posting, "company", None), office_id),
    }
