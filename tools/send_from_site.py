"""**사이트에 실제로 떠 있는 것**을 읽어서 텔레그램으로 보낸다.

tools/send_all.py 는 로컬 저장분을 읽는다. 그런데 진짜 저장분은 GitHub Actions 캐시에
있어서, 로컬에는 낡은 사본밖에 없다 (44건 vs 56건). 워크플로를 수동 실행할 수 없는
상황에서 같은 결과를 내려면 사이트가 발행한 data.json 을 읽는 수밖에 없다.

data.json 은 공개용이라 이름·학교가 [NAME]·[SCHOOL] 로 가려져 있다. 텔레그램은
비공개 그룹이므로 .env 의 실제 값으로 되돌려 보낸다 (사이트 렌더러도 화면에서 같은
자리를 채운다).

    ./.venv/bin/python tools/send_from_site.py --dry-run
    ./.venv/bin/python tools/send_from_site.py --gate open
    ./.venv/bin/python tools/send_from_site.py
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2 as httpx                                             # noqa: E402
from dotenv import load_dotenv                                     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from concurrent.futures import ThreadPoolExecutor, as_completed      # noqa: E402
import json                                                         # noqa: E402

from src import eligibility, i18n, notify, relevance, salary, verified  # noqa: E402
from src.match import assess                                        # noqa: E402
from src.models import Posting                                      # noqa: E402
from src.render import load_locale, render_posting                  # noqa: E402
from src.targets import load_config, load_offices                   # noqa: E402

SITE = "https://programmerson717.github.io/atelier-radar/data.json"
# 클라우드가 아직 못 옮긴 것을 여기서 옮겼을 때 담아 두는 자리. 다시 부르지 않으려고 남긴다.
CACHE = ROOT / "store" / "site_i18n_cache.json"


def unredact(v):
    """공개용으로 가린 자리를 실제 값으로 되돌린다. 값을 모르면 그대로 둔다."""
    if isinstance(v, str):
        for token, env in (("[NAME]", "CANDIDATE_NAME"), ("[SCHOOL]", "CANDIDATE_SCHOOL")):
            real = os.environ.get(env)
            if real:
                v = v.replace(token, real)
        return v
    if isinstance(v, list):
        return [unredact(x) for x in v]
    if isinstance(v, dict):
        return {k: unredact(x) for k, x in v.items()}
    return v


def _rebuild(x, off):
    """사이트 항목 하나에서 판정 객체들을 다시 만든다 (클라우드가 만든 것과 같은 코드)."""
    p = Posting(**{k: v for k, v in x.items() if k in Posting.model_fields})
    verified.apply(p)
    pc = x.get("country") or off.country
    a = assess(p, pc, off)
    e = eligibility.judge(p, pc)
    return p, pc, a, e, relevance.fit_grade(p, off, a), salary.describe(p, pc, off.tier, off.id)


def fill_missing(posts, by, cfg, lang, workers=3) -> dict:
    """옛 번역인 것만 여기서 옮긴다. 클라우드 저장분은 못 고치지만 보낼 것은 만들 수 있다."""
    from src.extract import _client

    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    # 사이트 data.json 은 번역 해시를 싣지 않는다. 그래서 "클라우드 것이 최신인가" 를
    # 밖에서는 알 수 없다 — 필드 유무로 짐작했더니, 마감·급여가 아예 없는 공고를
    # 죄다 '옛 번역' 으로 잘못 셌다. 여기서 옮긴 것만 해시로 확실히 안다.
    todo = []
    for x in posts:
        key = x.get("source_url") or x.get("title")
        off = by.get(x.get("office_id"))
        if off is None:
            continue
        p, _pc, a, e, fit, pay = _rebuild(x, off)
        bundle = i18n.bundle_of(i18n.display_source(p, a, e, fit[1], pay,
                                                    unredact(x.get("outreach"))))
        h = i18n.source_hash(bundle)
        if cache.get(key, {}).get("hash") == h:
            x["i18n"] = {**(x.get("i18n") or {}), **cache[key]["packs"]}
            continue
        todo.append((key, x, bundle, h))

    if not todo:
        return cache
    print(f"클라우드가 아직 못 옮긴 {len(todo)}건을 여기서 옮긴다 (동시 {workers})", file=sys.stderr)
    client = _client()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(i18n.translate, client, b, cfg): (k, x, h) for k, x, b, h in todo}
        done = 0
        for fut in as_completed(futs):
            key, x, h = futs[fut]
            try:
                packs = fut.result()
            except Exception as ex:
                print(f"  ✗ {x.get('title','')[:34]} — {type(ex).__name__}", file=sys.stderr)
                continue
            if not packs:
                continue
            x["i18n"] = {**(x.get("i18n") or {}), **packs}
            cache[key] = {"hash": h, "packs": packs}
            done += 1
            print(f"  ✓ [{done}/{len(todo)}] {x.get('title','')[:40]}", file=sys.stderr, flush=True)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


async def run(args) -> int:
    cfg = load_config()
    lang = (cfg.get("telegram") or {}).get("locale", "zh_TW")
    L = load_locale(lang)
    part_fmt = (L.get("bot") or {}).get("part")
    by = {o.id: o for o in load_offices()}

    data = httpx.get(args.url, timeout=60).json()
    posts = [x for x in data["postings"] if not x.get("archive")]
    print(f"사이트 {data['generated_at']} · 공고 {len(posts)}건", file=sys.stderr)

    # 사이트와 같은 순서 — 마감이 늦은 것부터 보내면 임박한 것이 맨 아래에 남는다
    posts.sort(key=lambda x: str(x.get("deadline") or ""), reverse=True)
    if args.gate:
        posts = [x for x in posts if x.get("gate") == args.gate]
    if args.limit:
        posts = posts[:args.limit]

    verified_keys = set()
    if args.fill_missing:
        verified_keys = set(fill_missing(posts, by, cfg, lang, args.workers))

    unsure = [x for x in posts
              if (x.get("source_url") or x.get("title")) not in verified_keys]
    if unsure and not args.allow_untranslated:
        print(f"번역이 최신인지 확인 못 한 공고가 {len(unsure)}건이다.\n"
              f"--fill-missing 으로 여기서 옮기거나, --allow-untranslated 로 그냥 보내라.",
              file=sys.stderr)
        return 1

    ok = fail = 0
    for i, x in enumerate(posts, 1):
        off = by.get(x.get("office_id"))
        if off is None:
            continue
        p, pc, a, e, fit, pay = _rebuild(x, off)
        tr = unredact((x.get("i18n") or {}).get(lang))
        kit = unredact(x.get("outreach"))

        text = render_posting(p, off, a, L, e, kit, pay, fit, tr=tr, lang=lang, country=pc)
        n = len(notify.chunks(text))
        where = pc + (" + OPEN" if e.gate == "open" else "")
        head = f"[{i}/{len(posts)}] {off.id} · {e.gate} → {where} · {n}통"
        if args.dry_run:
            print(head)
            print("─" * 60 + "\n" + text + "\n")
            continue
        delivered, failed = await notify.send_ok(text, country=pc, gate=e.gate,
                                                 part_fmt=part_fmt)
        print(f"{head} — {'보냄' if delivered else '실패'}"
              + (f" ({'; '.join(failed)[:140]})" if failed else ""), file=sys.stderr, flush=True)
        ok += bool(delivered)
        fail += (not delivered)
        if i < len(posts):
            await asyncio.sleep(args.delay)

    if not args.dry_run:
        print(f"\n끝 — 보냄 {ok}건 · 실패 {fail}건", file=sys.stderr)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=SITE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gate", help="open|ask|native|domestic|closed 중 하나만")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=3.0, help="메시지 간격(초)")
    ap.add_argument("--allow-untranslated", action="store_true")
    ap.add_argument("--fill-missing", action="store_true",
                    help="클라우드가 아직 못 옮긴 것을 여기서 옮겨서 보낸다")
    ap.add_argument("--workers", type=int, default=3)
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
