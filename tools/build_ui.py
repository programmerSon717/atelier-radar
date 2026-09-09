"""config/locales/*.yaml 의 web: 절 → site/ui.js 를 만든다.

웹과 텔레그램이 **같은 말**을 쓰게 하려고 문구를 한곳에 모았다. 예전에는 화면 문구가
site/ui.js 에, 봇 문구가 config/locales/*.yaml 에 따로 있어서 애초에 같아질 수가 없었다.

    ./.venv/bin/python tools/build_ui.py

ui.js 는 생성물이다. 직접 고치면 다음 실행에 덮인다.
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOC = ROOT / "config" / "locales"
OUT = ROOT / "site" / "ui.js"
LANGS = ("ko", "en", "zh_TW")

HEAD = """\
// 이 파일은 생성물이다 — 직접 고치지 마라.
// 문구는 config/locales/{ko,en,zh_TW}.yaml 의 web: 절에 있다.
// 고친 뒤 `./.venv/bin/python tools/build_ui.py` 를 돌린다.
// 공고 내용(JD)은 여기 없다. 그건 data.json 의 i18n 에 들어 있다 (tools/translate_postings.py).
"""


def strings(lang: str) -> dict:
    doc = yaml.safe_load((LOC / f"{lang}.yaml").read_text(encoding="utf-8")) or {}
    return doc.get("web") or {}


def build() -> str:
    packs = {l: strings(l) for l in LANGS}
    base = set(packs["ko"])
    for l in LANGS[1:]:
        missing, extra = base - set(packs[l]), set(packs[l]) - base
        if missing or extra:
            raise SystemExit(f"{l}.yaml 의 web: 키가 ko 와 다르다 — 빠짐 {sorted(missing)} / 남음 {sorted(extra)}")

    out = [HEAD, "const UI = {"]
    for l in LANGS:
        out.append(f"  {l}: {{")
        for k, v in packs[l].items():
            out.append(f"    {k}: {json.dumps(v, ensure_ascii=False)},")
        out.append("  },")
    out.append("};")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    js = build()
    if "--check" in sys.argv:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != js:
            raise SystemExit("site/ui.js 가 config/locales 와 어긋난다 — tools/build_ui.py 를 돌려라")
        print("ui.js 최신")
    else:
        OUT.write_text(js, encoding="utf-8")
        print(f"site/ui.js 생성 — {LANGS} × {len(strings('ko'))}개 문구")
