"""사이트가 읽을 data.json 을 만든다.

HTML 에 데이터를 구워 넣지 않고 분리한다. 그래야 페이지를 다시 만들지 않아도
데이터만 갈아끼우면 화면이 갱신되고, 브라우저에서 필터·정렬을 그때그때 할 수 있다.
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import eligibility                      # noqa: E402
from src.match import assess                     # noqa: E402
from src.models import Posting                   # noqa: E402
from src.targets import load_offices             # noqa: E402


def build() -> dict:
    offs = load_offices()
    by = {o.id: o for o in offs}
    db = ROOT / "store" / "radar.sqlite"
    sent, hashes = [], {}
    if db.exists():
        c = sqlite3.connect(db)
        sent = [(json.loads(p), t) for p, t in
                c.execute("SELECT payload, sent_at FROM sent_posting")]
        hashes = {r[0]: r for r in c.execute("SELECT office_id,hash,checked_at FROM page_hash")}

    offices = []
    for o in offs:
        h = hashes.get(o.id)
        offices.append({
            "id": o.id, "country": o.country, "name": o.display_name,
            "name_local": (o.name.get("ko") or o.name.get("ja") or o.name.get("zh")
                           or o.display_name),
            "city": o.city, "tier": o.tier, "url": o.careers_url,
            "checked_at": h[2] if h else None,
            "status": "ok" if (h and h[1]) else ("fail" if h else "untracked"),
        })

    posts = []
    for d, sent_at in sent:
        p = Posting(**d)
        off = by.get(p.office_id)
        if off is None:
            continue
        a = assess(p, off.country, off)
        e = eligibility.judge(p, off.country)
        posts.append({
            **d,
            "country": off.country, "office_name": off.display_name,
            "office_tier": off.tier, "sent_at": sent_at,
            "verdict": a.verdict, "expired": a.expired, "labels": a.labels,
            "blockers": a.blockers, "soft_blockers": a.soft_blockers,
            "gate": e.gate, "gate_icon": e.icon, "gate_label": e.label("ko"),
            "gate_reason": e.reason, "gate_evidence": e.evidence, "gate_action": e.action,
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offices": offices,
        "postings": posts,
    }


if __name__ == "__main__":
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    d = build()
    (docs / "data.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    g = {}
    for p in d["postings"]:
        g[p["gate"]] = g.get(p["gate"], 0) + 1
    print(f"data.json  공고 {len(d['postings'])}건  사무소 {len(d['offices'])}곳  게이트 {g}")
