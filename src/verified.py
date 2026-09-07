"""사람이 공고 원문을 직접 보고 확인한 사실. 모델 추출보다 우선한다.

추출 모델은 같은 페이지를 두 번 읽어도 다르게 답하고, 자격요건이 포스터 이미지에만
있으면 아예 못 읽기도 한다. 그렇게 틀린 판정이 사이트에 올라가면 재수집 전까지 그대로다.
그래서 눈으로 확인한 것은 여기에 박아 둔다 — 저장소에 있으니 클라우드도 같이 쓴다.

`data/verified/postings.yaml` 형식:

    postings:
      - url: https://...            # 공고 주소 (추적 파라미터는 무시하고 맞춘다)
        checked_at: "2026-09-07"
        source: "어디서 확인했는지 (예: 회사 채용페이지 포스터 이미지)"
        fields:                     # Posting 필드를 그대로 덮어쓴다
          domestic_degree_required: true
"""
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .store import normalize_url

PATH = Path(__file__).resolve().parent.parent / "data" / "verified" / "postings.yaml"


@lru_cache(maxsize=1)
def _index() -> dict[str, dict[str, Any]]:
    if not PATH.exists():
        return {}
    doc = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, Any]] = {}
    for e in doc.get("postings") or []:
        url = e.get("url")
        if not url or not e.get("fields"):
            continue
        out[normalize_url(url)] = e
    return out


def apply(posting):
    """확인된 사실을 공고에 덮어쓴다. 해당 없으면 그대로 돌려준다."""
    e = _index().get(normalize_url(getattr(posting, "source_url", "") or ""))
    if not e:
        return posting
    for k, v in (e.get("fields") or {}).items():
        if hasattr(posting, k):
            setattr(posting, k, v)
    note = f"사람이 원문 확인({e.get('checked_at', '')}) — {e.get('source', '')}"
    posting.notes = f"{note}. {posting.notes}" if posting.notes else note
    posting.confidence = "confirmed"
    return posting
