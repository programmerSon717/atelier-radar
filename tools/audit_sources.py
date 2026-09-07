"""발행한 내용을 공고 원문과 대조한다.

봇이 틀리는 방식은 정해져 있다 — 원문에 있는 결정적 한 줄(국내 대학 졸업 요건,
유학생 전형, 어학 급수, 경력 연수)을 못 읽고 "지원 가능" 으로 내보내는 것이다.
그래서 그 문구들을 원문에서 직접 찾아 우리가 발행한 판정과 맞춰본다. LLM 은 쓰지 않는다.

    ./.venv/bin/python tools/audit_sources.py            # 라이브 사이트 대조
    ./.venv/bin/python tools/audit_sources.py --local    # 로컬 DB 대조
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import eligibility, render_js                       # noqa: E402
from src.models import Posting                               # noqa: E402
from src.scope import country_of                             # noqa: E402
from src.watch import extract_text, find_company_apply_links, find_body_iframes  # noqa: E402

LIVE = "https://programmerson717.github.io/atelier-radar/data.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128.0 Safari/537.36"}

# 원문에 이게 있으면 우리 판정이 이래야 한다
RULES = [
    ("국내대 졸업 요건", re.compile(r"국내\s*(?:정규\s*)?[24]년제|국내\s*정규\s*대학|"
                              r"국내\s*소재\s*대학|국내\s*대학\s*(?:졸업|재학)|"
                              r"日本国内の大学|国内の大学を(?:卒業|修了)"), {"domestic"}),
    ("유학생 전형", re.compile(r"외국인\s*유학생|유학생\s*(?:채용|전형)|外国人留学生"), {"domestic"}),
    ("어학시험 요구", re.compile(r"TOPIK|한국어능력시험|JLPT|日本語能力試験|"
                            r"TOEIC\s*\d{3}|OPIC?\s*IM|토익\s*\d{3}"), {"domestic", "native", "closed"}),
    ("경력 요구", re.compile(r"경력\s*[1-9]\d?\s*년\s*이상|[1-9]\d?\s*年以上の?(?:実務)?経験|"
                          r"[一二三四五六七八九十兩两]\s*年以上"), set()),
    ("학력무관", re.compile(r"학력\s*무관|학력\s*불문|學歷不拘|学歴不問"), set()),
]


def fetch_text(url: str, follow_company: bool) -> str:
    """공고 원문 텍스트. 잡보드면 회사 채용페이지까지 따라간다 (거기 자격요건이 있다)."""
    text = ""
    try:
        with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as c:
            r = c.get(url)
            html = r.text
            text = extract_text(html)
            for fr in find_body_iframes(html, str(r.url))[:2]:
                try:
                    text += " " + extract_text(c.get(fr, follow_redirects=True).text)
                except Exception:
                    pass
            if follow_company:
                for capp in find_company_apply_links(html, str(r.url)):
                    c_html, _ = render_js.render(capp, timeout_ms=35_000)
                    if c_html:
                        text += " [회사페이지] " + extract_text(c_html)
    except Exception as e:
        return f"__FETCH_FAIL__ {type(e).__name__}"
    if len(text) < 200:                     # JS 껍데기면 브라우저로 한 번 더
        h, _ = render_js.render(url, timeout_ms=35_000)
        if h:
            text = extract_text(h)
    return text


def _gate_of(d: dict) -> str | None:
    """로컬 DB 행에는 게이트가 없다 (발송 시점에 계산한다). 지금 코드로 다시 매긴다."""
    try:
        p = Posting(**{k: v for k, v in d.items() if k in Posting.model_fields})
        return eligibility.judge(p, country_of(p, d.get("country") or "KR")).gate
    except Exception:
        return None


def load_postings(local: bool) -> list[dict]:
    if not local:
        return httpx.get(LIVE, timeout=30).json()["postings"]
    db = sqlite3.connect(Path(__file__).resolve().parent.parent / "store" / "radar.sqlite")
    out = []
    for (pl,) in db.execute("SELECT payload FROM sent_posting"):
        d = json.loads(pl)
        out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="라이브 대신 로컬 DB 를 대조")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    posts = load_postings(args.local)
    if args.limit:
        posts = posts[:args.limit]

    bad, checked, failed = [], 0, []
    for p in posts:
        url = p.get("source_url") or ""
        if not url.startswith("http"):
            continue
        gate = p.get("gate") or _gate_of(p)
        is_board = "jobkorea" in url or "saramin" in url
        text = fetch_text(url, follow_company=is_board and gate in ("open", "ask", None))
        if text.startswith("__FETCH_FAIL__"):
            failed.append((p.get("title", "")[:34], text))
            continue
        checked += 1
        for name, rx, want_gates in RULES:
            m = rx.search(text)
            if not m:
                continue
            if want_gates and gate in want_gates:
                continue          # 이미 제대로 잡고 있다
            if not want_gates:    # 아예 나가면 안 되는 종류
                bad.append((p.get("title", "")[:34], gate, name, m.group(0)[:24], url))
            else:
                bad.append((p.get("title", "")[:34], gate, name, m.group(0)[:24], url))

    print(f"\n대조 {checked}건 / 실패 {len(failed)}건 / 어긋남 {len(bad)}건\n")
    for t, gate, name, ev, url in bad:
        print(f"  ✗ [{gate}] {t:36} | 원문에 {name}: “{ev}”")
        print(f"      {url[:110]}")
    for t, e in failed:
        print(f"  ? 원문 확인 실패 — {t}: {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
