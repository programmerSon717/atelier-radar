"""저장된 공고를 한국어·영어·번체중문 세 벌로 만들어 DB 에 넣는다.

화면은 저장분으로 그려진다. 그래서 번역도 저장분에 넣어야 한다.
내용이 바뀌지 않은 공고는 건너뛴다 (원문 해시 비교) — 호출을 아끼려는 것이다.

    ./.venv/bin/python tools/translate_postings.py            # 안 된 것만
    ./.venv/bin/python tools/translate_postings.py --all      # 전부 다시
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv                                     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from src import eligibility, i18n, relevance, salary               # noqa: E402
from src.extract import _client                                    # noqa: E402
from src.match import assess, is_new_grad_ok                       # noqa: E402
from src.models import Posting                                     # noqa: E402
from src.scope import country_of                                   # noqa: E402
from src.targets import load_config, load_offices                  # noqa: E402
from src import verified                                           # noqa: E402


def display_bundle(d: dict, off) -> dict:
    """화면에 나가는 것 전부 — 공고 원문 필드 + 우리가 만든 판정 문구."""
    p = Posting(**{k: v for k, v in d.items() if k in Posting.model_fields})
    verified.apply(p)
    pc = country_of(p, off.country)
    a = assess(p, pc, off)
    e = eligibility.judge(p, pc)
    fit, fit_why = relevance.fit_grade(p, off, a)
    pay = salary.describe(p, pc, off.tier, off.id)
    src = {
        **{k: getattr(p, k, None) for k in i18n.FIELDS_TEXT if hasattr(p, k)},
        "responsibilities": p.responsibilities, "qualifications": p.qualifications,
        "preferred": p.preferred, "firm_projects": p.firm_projects,
        "blockers_desc": a.blockers_desc, "soft_desc": a.soft_desc,
        "met": a.met, "unknowns": a.unknowns,
        "gate_label": e.label("ko"), "gate_reason": e.reason,
        "gate_evidence": e.evidence, "gate_action": e.action,
        "fit_why": fit_why,
        "pay_note": (pay.get("company_avg") or {}).get("basis"),
    }
    return i18n.bundle_of(src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="이미 번역된 것도 다시")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config()
    by = {o.id: o for o in load_offices()}
    conn = sqlite3.connect(ROOT / "store" / "radar.sqlite")
    rows = conn.execute("SELECT key, payload FROM sent_posting").fetchall()

    client = _client()
    done = skipped = failed = 0
    for key, pl in rows:
        d = json.loads(pl)
        off = by.get(d.get("office_id"))
        if off is None:
            continue
        try:
            p = Posting(**{k: v for k, v in d.items() if k in Posting.model_fields})
            if not is_new_grad_ok(assess(p, off.country, off), p.track):
                continue          # 어차피 안 실리는 공고는 옮기지 않는다
        except Exception:
            continue

        bundle = display_bundle(d, off)
        h = i18n.source_hash(bundle)
        cur = d.get("_i18n") or {}
        if not args.all and cur.get("hash") == h:
            skipped += 1
            continue

        out = i18n.translate(client, bundle, cfg)
        if not out:
            failed += 1
            print(f"  ✗ {d.get('title','')[:40]}")
            continue
        d["_i18n"] = {"hash": h, **out}
        conn.execute("UPDATE sent_posting SET payload=? WHERE key=?",
                     (json.dumps(d, ensure_ascii=False), key))
        conn.commit()
        done += 1
        print(f"  ✓ {d.get('title','')[:40]:42} → {out['ko'].get('title','')[:30]}")
        if args.limit and done >= args.limit:
            break

    print(f"\n번역 {done}건 · 그대로 {skipped}건 · 실패 {failed}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
