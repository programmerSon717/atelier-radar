"""사이트가 읽을 data.json 을 만든다.

HTML 에 데이터를 구워 넣지 않고 분리한다. 그래야 페이지를 다시 만들지 않아도
데이터만 갈아끼우면 화면이 갱신되고, 브라우저에서 필터·정렬을 그때그때 할 수 있다.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import eligibility, relevance, salary, verified                      # noqa: E402
from src.match import assess, is_new_grad_ok
from src.scope import country_of                     # noqa: E402
from src.models import Posting                   # noqa: E402
from src.targets import load_offices             # noqa: E402


# ── 공개 사이트로 나가는 것에서 신원을 지운다 ───────────────────
# 메일 초안 서명에 본인 이름이, 본문에 학교 이름이 들어간다. docs/ 는 GitHub Pages 로
# 그대로 공개되므로 여기서 반드시 가린다. 텔레그램(비공개 그룹)에는 실명 그대로 나간다.
def _identity_known() -> bool:
    """가릴 대상을 알고 있는가. 모르면 메일 초안을 아예 싣지 않는다 (실패-차단)."""
    return bool(os.environ.get("CANDIDATE_NAME"))


def _redact(v):
    if isinstance(v, str):
        for env, mask in (("CANDIDATE_NAME", "(지원자 이름)"),
                          ("CANDIDATE_SCHOOL", "(대학원)")):
            real = os.environ.get(env)
            if real:
                v = v.replace(real, mask)
                # "컬럼비아 대학원(GSAPP)" 을 넘겨도 모델은 "컬럼비아 대학교" 로 풀어 쓴다.
                # 괄호·수식어를 뗀 알맹이도 같이 가린다.
                # "Jasmin (Jia-Chen) Lin" 처럼 여러 토막인 이름은 성만 따로 쓰이기도 한다.
                # 학교도 "컬럼비아 대학원(GSAPP)" 을 넘기면 "컬럼비아 대학교" 로 풀어 쓴다.
                for tok in re.split(r"[()（）,·\s]+", real.strip()):
                    if len(tok) >= 2:
                        v = v.replace(tok, mask)
                v = re.sub(rf"(?:{re.escape(mask)}[\s·]*)+", mask, v)
        return v
    if isinstance(v, list):
        return [_redact(x) for x in v]
    if isinstance(v, dict):
        return {k: _redact(x) for k, x in v.items()}
    return v


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
        verified.apply(p)          # 확인된 사실이 있으면 저장분보다 우선한다
        d = {**d, **p.model_dump()}
        off = by.get(p.office_id)
        if off is None:
            continue
        pc = country_of(p, off.country)
        a = assess(p, pc, off)
        if not is_new_grad_ok(a, p.track):
            continue   # 경력직은 사이트에도 싣지 않는다
        if relevance.career_only(p) or relevance.special_track(p):
            continue
        if relevance.is_low_fit(relevance.label(p, off)):
            continue   # 설계직 아님·시공사
        if not relevance.worth_applying(p, off)[0]:
            continue   # 이름 모를 사무소는 사이트에도 싣지 않는다 (발송 기준과 동일)
        if relevance.drop_for_no_degree(p, off):
            continue   # 학력무관 공고는 사이트에도 싣지 않는다 (발송 단계와 같은 기준)
        grade, grade_why = relevance.firm_grade(p, off)
        if grade == "weak":
            continue
        fit_grade, fit_why = relevance.fit_grade(p, off, a)
        e = eligibility.judge(p, pc)
        pay = salary.describe(p, pc, off.tier)
        posts.append({
            # _outreach 원본(실명이 들어 있다)이 그대로 실리지 않게 밑줄 키는 빼고 펼친다.
            # 아래에서 가린 사본만 "outreach" 로 싣는다.
            **{k: v for k, v in d.items() if not k.startswith("_")},
            "country": pc, "office_name": off.display_name,
            "office_tier": off.tier, "sent_at": sent_at,
            "verdict": a.verdict, "expired": a.expired,
            "blockers_desc": a.blockers_desc, "soft_desc": a.soft_desc,
            "met": a.met, "unknowns": a.unknowns,
            "gate": e.gate, "gate_icon": e.icon, "gate_label": e.label("ko"),
            # 이름을 모르는 채로 공개 사이트에 메일 초안을 싣지 않는다.
            # (워크플로에서 시크릿을 안 넘기면 여기서 통째로 빠진다)
            "outreach": _redact(d.get("_outreach")) if _identity_known() else None,
            "grade": grade, "grade_why": grade_why, "pay": pay,
            "fit": fit_grade, "fit_why": fit_why,
            "gate_reason": e.reason, "gate_evidence": e.evidence, "gate_action": e.action,
        })

    # 같은 공고가 두 번 실리는 일이 있다. 잡보드에서 목록 URL 로 한 번, 상세 URL 로
    # 또 한 번 들어오면 키가 갈린다. 화면에서는 회사+제목이 같으면 한 건으로 합치고,
    # **내용이 더 채워진 쪽**을 남긴다 (빈 판독이 채워진 판독을 덮으면 안 된다).
    def _richness(x: dict) -> tuple:
        return (
            sum(1 for k in ("qualifications", "responsibilities", "preferred",
                            "software", "firm_projects") if x.get(k)),
            0 if x.get("gate") == "ask" else 1,     # 판정이 선 쪽을 우선한다
            len(json.dumps(x, ensure_ascii=False)),
        )

    dedup: dict[tuple, dict] = {}
    for x in posts:
        k = ("".join((x.get("company") or x.get("office_name") or "").split()).lower(),
             "".join((x.get("title") or "").split()).lower())
        if k not in dedup or _richness(x) > _richness(dedup[k]):
            dedup[k] = x
    posts = list(dedup.values())

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
