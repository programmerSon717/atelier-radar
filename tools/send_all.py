"""사이트에 떠 있는 공고를 **그대로** 텔레그램에 다시 보낸다.

거르는 기준은 tools/export_data.selected() 한곳에서 온다 — 사이트에 실리는 목록과
같은 목록이다. 순서도 사이트와 같다 (마감 늦은 것부터 → 임박한 것이 마지막에 뜬다).

    ./.venv/bin/python tools/send_all.py --dry-run      # 몇 건이 어디로 갈지만 본다
    ./.venv/bin/python tools/send_all.py                # 실제로 보낸다
    ./.venv/bin/python tools/send_all.py --gate open    # 지원 가능한 것만
    ./.venv/bin/python tools/send_all.py --limit 5

텔레그램 그룹은 분당 20통 제한이 있다. --delay 로 간격을 준다 (기본 3초).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv                                     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from src import notify                                             # noqa: E402
from src.render import load_locale, render_posting                 # noqa: E402
from src.targets import load_config                                # noqa: E402
from src import i18n                                               # noqa: E402
from tools.export_data import selected                             # noqa: E402
from tools.translate_postings import display_bundle                # noqa: E402


async def run(args) -> int:
    cfg = load_config()
    lang = (cfg.get("telegram") or {}).get("locale", "zh_TW")
    L = load_locale(lang)
    part_fmt = (L.get("bot") or {}).get("part")

    rows = selected()
    # 사이트와 같은 순서 — 마감이 늦은 것부터 보내면 임박한 것이 맨 아래(가장 잘 보이는
    # 자리)에 남는다. site/app.js 의 정렬과 같다.
    rows.sort(key=lambda r: str(r.payload.get("deadline") or ""), reverse=True)
    if args.gate:
        rows = [r for r in rows if r.elig.gate == args.gate]
    if args.limit:
        rows = rows[:args.limit]

    # 번역이 있는지만 보면 부족하다. 프롬프트를 고치면 옛 번역이 그대로 남아 있어서
    # '있긴 있는' 상태가 된다 — 그걸 보내면 예전 문구가 다시 나간다.
    stale = []
    for r in rows:
        cur = r.payload.get("_i18n") or {}
        if not cur.get(lang):
            stale.append((r, "번역 없음"))
            continue
        want = i18n.source_hash(display_bundle(r.payload, r.office))
        if cur.get("hash") != want:
            stale.append((r, "옛 번역"))
    if stale and not args.allow_untranslated:
        why = {}
        for _r, k in stale:
            why[k] = why.get(k, 0) + 1
        print(f"보낼 수 없다 — {', '.join(f'{k} {v}건' for k, v in why.items())}. 먼저 옮겨라:\n"
              f"    ./.venv/bin/python tools/translate_postings.py\n"
              f"그래도 보내려면 --allow-untranslated", file=sys.stderr)
        return 1

    print(f"{len(rows)}건 · 언어 {lang} · "
          f"{'미리보기' if args.dry_run else '발송'} (간격 {args.delay}초)", file=sys.stderr)

    ok = fail = 0
    for i, r in enumerate(rows, 1):
        tr = (r.payload.get("_i18n") or {}).get(lang)
        text = render_posting(r.posting, r.office, r.assess, L, r.elig,
                              r.payload.get("_outreach"), r.pay, r.fit,
                              tr=tr, lang=lang, country=r.country)
        n = len(notify.chunks(text))
        where = r.country + (" + OPEN" if r.elig.gate == "open" else "")
        head = f"[{i}/{len(rows)}] {r.office.id} · {r.elig.gate} → {where} · {n}통"
        if args.dry_run:
            print(head)
            print("─" * 60 + "\n" + text + "\n")
            continue
        delivered, failed = await notify.send_ok(text, country=r.country, gate=r.elig.gate,
                                                 part_fmt=part_fmt)
        print(f"{head} — {'보냄' if delivered else '실패'}"
              + (f" ({'; '.join(failed)[:120]})" if failed else ""), file=sys.stderr)
        ok += bool(delivered)
        fail += (not delivered)
        if i < len(rows):
            await asyncio.sleep(args.delay)

    if not args.dry_run:
        print(f"\n끝 — 보냄 {ok}건 · 실패 {fail}건", file=sys.stderr)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 내용만 출력")
    ap.add_argument("--gate", help="open|ask|native|domestic|closed 중 하나만")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=3.0, help="메시지 간격(초)")
    ap.add_argument("--allow-untranslated", action="store_true",
                    help="번역이 없거나 옛 번역이어도 그대로 보낸다")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
