"""현재 상태로 정적 사이트(docs/index.html)를 만든다.

봇을 돌릴 때마다 같이 갱신되어 GitHub Pages 로 배포된다.
클로드 계정 없이 링크만으로 볼 수 있다.

    ./.venv/bin/python tools/build_site.py
"""
import html
import json
import sqlite3
import sys
from datetime import date, timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.match import assess                      # noqa: E402
from src.models import Posting                    # noqa: E402
from src.targets import load_offices              # noqa: E402


def collect() -> dict:
    offs = load_offices()
    by = {o.id: o for o in offs}
    db = ROOT / "store" / "radar.sqlite"
    sent, hashes = [], {}
    if db.exists():
        c = sqlite3.connect(db)
        sent = [json.loads(p) for (p,) in c.execute("SELECT payload FROM sent_posting")]
        hashes = {r[0]: r for r in c.execute("SELECT office_id,hash,fail_count FROM page_hash")}
    out = {"offices": [], "postings": []}
    for o in offs:
        h = hashes.get(o.id)
        out["offices"].append(dict(
            id=o.id, country=o.country, name=o.display_name,
            name_local=(o.name.get("ko") or o.name.get("ja") or o.name.get("zh") or o.display_name),
            city=o.city, tier=o.tier, url=o.careers_url,
            status=("ok" if (h and h[1]) else ("fail" if h else "untracked"))))
    for d in sent:
        p = Posting(**d)
        off = by.get(p.office_id)
        if off is None:
            continue
        a = assess(p, off.country, off)
        out["postings"].append(dict(**d, country=off.country, office_name=off.display_name,
                                    verdict=a.verdict, labels=a.labels))
    return out


D = collect()
E = lambda s: html.escape(str(s or ""), quote=True)
CN = {"KR": "한국", "JP": "일본", "TW": "대만"}
VN = {"fit": "지원 가능", "conditional": "조건부", "blocked": "요건 미달",
      "expired": "마감", "unknown": "확인 필요"}

offs, posts = D["offices"], D["postings"]
tracked = sum(1 for o in offs if o["status"] == "ok")

# ── 커버리지 ──
cov = ""
for c in ("KR", "JP", "TW"):
    g = [o for o in offs if o["country"] == c]
    ok = sum(1 for o in g if o["status"] == "ok")
    n = sum(1 for p in posts if p["country"] == c)
    cov += f'''<div class="cov"><div class="cov-top"><span class="cov-name">{CN[c]}</span>
<span class="cov-num">{ok}/{len(g)} 추적 · 공고 {n}</span></div>
<div class="bar"><i class="b-ok" style="flex:{ok or 0}"></i><i class="b-no" style="flex:{len(g)-ok}"></i></div></div>'''

# ── 공고 schedule ──
def tags(p):
    t = []
    for l in p["labels"]:
        k = l[:2].strip()
        cls = ("block" if k in ("🔴", "⛔️") else "warn" if k in ("🟡", "⏰", "🏗", "🔧")
               else "good" if k in ("🟢", "🌏") else "")
        t.append(f'<span class="tag {cls}">{E(l)}</span>')
    if p.get("deadline"):
        t.insert(0, f'<span class="tag due">마감 {E(p["deadline"])}</span>')
    return "".join(t)

def jd(p):
    b = ""
    for key, lab in (("responsibilities", "담당 업무"), ("qualifications", "자격 요건"),
                     ("preferred", "우대 사항")):
        if p.get(key):
            li = "".join(f"<li>{E(x)}</li>" for x in p[key][:6])
            b += f"<div><h4>{lab}</h4><ul>{li}</ul></div>"
    if p.get("software"):
        b += f'<div><h4>요구 툴</h4><p>{E(" · ".join(p["software"][:10]))}</p></div>'
    facts = [f"{k}: {p[f]}" for f, k in (("employment_type", "고용형태"),
             ("salary", "급여"), ("process", "전형")) if p.get(f)]
    if facts:
        b += "<div><h4>조건</h4><p>" + "<br>".join(E(x) for x in facts) + "</p></div>"
    if p.get("notes"):
        b += f'<div><h4>확인 안 됨</h4><p>{E(p["notes"])}</p></div>'
    return f'<details><summary>상세 보기</summary><div class="jd">{b}</div></details>' if b else ""

order = {"fit": 0, "conditional": 1, "unknown": 2, "blocked": 3, "expired": 4}
rows = ""
for p in sorted(posts, key=lambda x: (order.get(x["verdict"], 9), x["country"])):
    rows += f'''<article class="row" data-v="{p['verdict']}" data-c="{p['country']}">
<div class="stripe"></div><div class="body">
<div class="r1"><span class="title">{E(p['title'])}</span>
<span class="firm">{E(p.get('company') or p['office_name'])} · {E(p.get('location') or CN[p['country']])} · {VN.get(p['verdict'], '')}</span></div>
<div class="r2">{tags(p)}</div>
<p class="sum">{E(p.get('summary'))}</p>{jd(p)}
<p style="margin:10px 0 0"><a class="src" href="{E(p['source_url'])}" target="_blank" rel="noopener">공고 원문 →</a></p>
</div></article>'''

untracked = [o for o in offs if o["status"] != "ok"]
gaps = "".join(f'<span class="gapitem">{E(o["name_local"])} <span style="opacity:.55">{o["country"]}</span></span>'
               for o in untracked)

BODY = f'''<div class="sheet">
<header class="titleblock">
  <div class="tb tb-lead">
    <h1>Atelier Radar</h1>
    <p class="sub">일본 · 한국 · 대만 건축설계 신입공채 및 인턴 추적</p>
  </div>
  <div class="tb"><span class="mark">대상</span>
    <div class="val" style="font-size:14px">Jasmin (Jia-Chen) Lin</div>
    <div class="sub" style="font-size:12.5px">Columbia GSAPP M.Arch · 2027.05 졸업</div></div>
  <div class="tb"><span class="mark">추적 사무소</span>
    <div class="val">{tracked}<small> / {len(offs)}</small></div></div>
  <div class="tb"><span class="mark">수집 공고</span>
    <div class="val">{len(posts)}<small> 건</small></div></div>
  <div class="tb"><span class="mark">최종 확인</span>
    <div class="val" style="font-size:14px">{date.today().isoformat()}</div></div>
</header>

<section class="coverage">{cov}</section>

<div class="schedhead">
  <h2>공고 일람</h2>
  <div class="filters" role="group" aria-label="국가 필터">
    <button class="chip" data-f="all" aria-pressed="true">전체</button>
    <button class="chip" data-f="KR" aria-pressed="false">한국</button>
    <button class="chip" data-f="JP" aria-pressed="false">일본</button>
    <button class="chip" data-f="TW" aria-pressed="false">대만</button>
  </div>
</div>
<div class="rows" id="rows">{rows}</div>

<section class="gap">
  <span class="mark">아직 추적하지 못하는 사무소 — {len(untracked)}곳</span>
  <p class="note">채용 페이지 주소를 아직 못 찾았거나, 자바스크립트로 그려서 본문을 읽을 수 없는 곳이다.
  여기 있는 동안은 공고가 올라와도 잡히지 않는다.</p>
  <div class="gaplist">{gaps}</div>
</section>

<footer><span>출처는 각 사무소 채용 페이지 및 잡보드 원문</span>
<span>확인되지 않은 항목은 추정하지 않고 비워 둔다</span></footer>
</div>

<script>
const rows=document.getElementById('rows');
document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('.chip').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
  const f=b.dataset.f;
  rows.querySelectorAll('.row').forEach(r=>
    r.classList.toggle('hide', f!=='all' && r.dataset.c!==f));
}}));
</script>'''

docs = ROOT / "docs"
docs.mkdir(exist_ok=True)
head = (ROOT / "site" / "_head.html").read_text(encoding="utf-8")
(docs / "index.html").write_text(head + BODY + "\n</body>\n</html>\n", encoding="utf-8")
(docs / ".nojekyll").write_text("", encoding="utf-8")   # _head 같은 밑줄 경로가 무시되지 않게
print(f"docs/index.html  공고 {len(posts)}건 / 추적 {tracked}/{len(offs)}")
