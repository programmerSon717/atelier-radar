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

from src import eligibility, notify, relevance, salary, verified    # noqa: E402
from src.match import assess                                        # noqa: E402
from src.models import Posting                                      # noqa: E402
from src.render import load_locale, render_posting                  # noqa: E402
from src.targets import load_config, load_offices                   # noqa: E402

SITE = "https://programmerson717.github.io/atelier-radar/data.json"


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

    stale = [x for x in posts if not (((x.get("i18n") or {}).get(lang) or {}).get("deadline_text")
                                      or ((x.get("i18n") or {}).get(lang) or {}).get("pay_stated"))]
    if stale and not args.allow_untranslated:
        print(f"아직 옛 번역인 공고가 {len(stale)}건이다. 번역이 끝난 뒤에 보내라.\n"
              f"그래도 보내려면 --allow-untranslated", file=sys.stderr)
        return 1

    ok = fail = 0
    for i, x in enumerate(posts, 1):
        off = by.get(x.get("office_id"))
        if off is None:
            continue
        p = Posting(**{k: v for k, v in x.items() if k in Posting.model_fields})
        verified.apply(p)
        pc = x.get("country") or off.country
        a = assess(p, pc, off)
        e = eligibility.judge(p, pc)
        fit = relevance.fit_grade(p, off, a)
        pay = salary.describe(p, pc, off.tier, off.id)
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
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
