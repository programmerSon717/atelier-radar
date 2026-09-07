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

from src import eligibility, relevance, salary                      # noqa: E402
from src.match import assess, is_new_grad_ok
from src.scope import country_of                     # noqa: E402
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
        pc = country_of(p, off.country)
        a = assess(p, pc, off)
        if not is_new_grad_ok(a, p.track):
            continue   # 경력직은 사이트에도 싣지 않는다
        grade, grade_why = relevance.firm_grade(p, off)
        if grade == "weak":
            continue
        e = eligibility.judge(p, pc)
        pay = salary.describe(p, pc, off.tier)
        posts.append({
            **d,
            "country": pc, "office_name": off.display_name,
            "office_tier": off.tier, "sent_at": sent_at,
            "verdict": a.verdict, "expired": a.expired,
            "blockers_desc": a.blockers_desc, "soft_desc": a.soft_desc,
            "met": a.met, "unknowns": a.unknowns,
            "gate": e.gate, "gate_icon": e.icon, "gate_label": e.label("ko"),
            "outreach": d.get("_outreach"),
            "grade": grade, "grade_why": grade_why, "pay": pay,
            "gate_reason": e.reason, "gate_evidence": e.evidence, "gate_action": e.action,
        })

    # 아카이브(과거 공고) — LLM 을 거치지 않고 목록에서 직접 긁은 가벼운 기록이다.
    # JD 는 없지만 '누가 언제 뽑았나' 는 알 수 있어서 내년 시점을 잡는 데 쓰인다.
    archive = []
    if db.exists():
        try:
            for url, country, company, title, posted, deadline, src in c.execute(
                "SELECT url,country,company,title,posted_at,deadline,source FROM archive"
                " ORDER BY COALESCE(posted_at,'') DESC"
            ):
                archive.append({"url": url, "country": country or "KR", "company": company,
                                "title": title, "posted_at": posted, "deadline": deadline,
                                "source": src})
        except sqlite3.OperationalError:
            pass   # 아직 아카이브를 한 번도 안 돌렸다

    return {
        "archive": archive,
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
