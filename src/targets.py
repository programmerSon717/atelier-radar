"""data/targets/*.yaml 과 profile.yaml 로더."""
from dataclasses import dataclass
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
