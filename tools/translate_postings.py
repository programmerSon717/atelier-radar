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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """화면에 나가는 것 전부 — 공고 원문 필드 + 우리가 만든 판정 문구.

    필드 목록은 src/i18n.display_source 한곳에서 온다 (봇도 같은 것을 쓴다)."""
    p = Posting(**{k: v for k, v in d.items() if k in Posting.model_fields})
    verified.apply(p)
    pc = country_of(p, off.country)
    a = assess(p, pc, off)
    e = eligibility.judge(p, pc)
    _fit, fit_why = relevance.fit_grade(p, off, a)
    pay = salary.describe(p, pc, off.tier, off.id)
    src = i18n.display_source(p, a, e, fit_why, pay, d.get("_outreach") or None)
    return i18n.bundle_of(src)


def _todo(conn, by, args) -> list[tuple]:
    """옮겨야 할 것만 고른다 — (key, payload, bundle, hash)."""
    out, skipped = [], 0
    for key, pl in conn.execute("SELECT key, payload FROM sent_posting").fetchall():
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
        # 내용이 그대로여도 **옮기다 만 자리가 남아 있으면** 다시 한다. 안 그러면
        # 해시가 같다는 이유로 영영 건너뛰고, 그 조각은 화면에 원문으로 남는다.
        left = i18n._hangul_left(cur) if cur else []
        if not args.all and cur.get("hash") == h and not left:
            skipped += 1
            continue
        if left:
            print(f"  ↻ 남은 자리 {len(left)}개 다시: {d.get('title','')[:32]}")
        out.append((key, d, bundle, h))
        if args.limit and len(out) >= args.limit:
            break
    return out, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="이미 번역된 것도 다시")
    ap.add_argument("--limit", type=int, default=0)
    # 한 건이 수십 초다. 순서대로 돌리면 50여 건에 한 시간이 넘어간다.
    ap.add_argument("--workers", type=int, default=3, help="동시 호출 수")
    args = ap.parse_args()

    cfg = load_config()
    by = {o.id: o for o in load_offices()}
    conn = sqlite3.connect(ROOT / "store" / "radar.sqlite")
    todo, skipped = _todo(conn, by, args)
    print(f"옮길 것 {len(todo)}건 · 그대로 {skipped}건 · 동시 {args.workers}")

    client = _client()
    done = failed = 0
    # 쓰기는 메인 스레드에서만 한다 (sqlite 연결을 스레드 간에 나눠 쓰지 않는다)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(i18n.translate, client, b, cfg): (k, d, h)
                for k, d, b, h in todo}
        for fut in as_completed(futs):
            key, d, h = futs[fut]
            try:
                out = fut.result()
            except Exception as e:
                out = None
                print(f"  ✗ {d.get('title','')[:36]} — {type(e).__name__}: {str(e)[:60]}")
            if not out:
                failed += 1
                continue
            d["_i18n"] = {"hash": h, **out}
            conn.execute("UPDATE sent_posting SET payload=? WHERE key=?",
                         (json.dumps(d, ensure_ascii=False), key))
            conn.commit()
            done += 1
            print(f"  ✓ [{done}/{len(todo)}] {d.get('title','')[:38]:40} "
                  f"→ {out['ko'].get('title','')[:28]}", flush=True)

    print(f"\n번역 {done}건 · 그대로 {skipped}건 · 실패 {failed}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
