"""data/targets/*.yaml 과 profile.yaml 로더."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "data" / "targets"
PROFILE_PATH = ROOT / "data" / "profile" / "profile.yaml"
CONFIG_PATH = ROOT / "config" / "settings.yaml"


@dataclass
class Office:
    id: str
    country: str
    name: dict[str, str]
    city: Optional[str]
    tier: Optional[str]
    careers_url: Optional[str]
    hiring_types: list[str]
    eng_ok: Optional[str]
    priority: str
    note: Optional[str]
    raw: dict[str, Any]

    @property
    def display_name(self) -> str:
        for k in ("en", "ko", "ja", "zh"):
            if k in self.name:
                return self.name[k]
        return self.id


def load_offices() -> list[Office]:
    offices: list[Office] = []
    for path in sorted(TARGET_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        country = doc.get("country", "??")
        for o in doc.get("offices") or []:
            offices.append(
                Office(
                    id=o["id"],
                    country=country,
                    name=o.get("name") or {},
                    city=o.get("city"),
                    tier=o.get("tier"),
                    careers_url=o.get("careers_url"),
                    hiring_types=o.get("hiring_types") or [],
                    eng_ok=o.get("eng_ok"),
                    priority=o.get("priority", "normal"),
                    note=o.get("note"),
                    raw=o,
                )
            )
    return offices


_CORP = re.compile(r"\(\s*주\s*\)|㈜|주식\s*회사|\(\s*유\s*\)|유한\s*회사|"
                   r"株式会社|㈱|股份有限公司|有限公司|Co\.?,?\s*Ltd\.?|Inc\.?|LLC", re.I)


def _norm_name(s: str) -> str:
    return re.sub(r"[\s·,.\-_'\"]+", "", _CORP.sub("", s or "")).lower()


@lru_cache(maxsize=1)
def _name_index() -> dict[str, "Office"]:
    """사무소 이름 → Office. 잡보드로 들어온 공고가 우리가 아는 곳인지 알아보려고 쓴다."""
    idx: dict[str, Office] = {}
    for o in load_offices():
        if o.tier == "job_board":
            continue
        for v in o.name.values():
            n = _norm_name(v)
            if len(n) >= 3:
                idx[n] = o
    return idx


def match_office(*texts: Optional[str]) -> Optional["Office"]:
    """회사명(또는 제목)이 우리 추적 목록의 사무소와 같은 곳인지 찾는다.

    잡보드 공고는 office 가 게시판이라 tier 로는 판단할 수 없다. 원오원아키텍스의
    신입공채가 vmspace 를 통해 들어와도 '이름 모를 사무소' 로 취급되던 이유다."""
    idx = _name_index()
    for t in texts:
        n = _norm_name(t or "")
        if len(n) < 3:
            continue
        if n in idx:
            return idx[n]
        for key, off in idx.items():
            if key in n or n in key:
                return off
    return None


def load_profile() -> dict[str, Any]:
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def job_boards() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in sorted(TARGET_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out[doc.get("country", "??")] = doc.get("job_boards") or []
    return out
