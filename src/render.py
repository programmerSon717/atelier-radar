"""텔레그램 메시지 만들기. 문구는 전부 config/locales/*.yaml 에서 온다.
ko → zh_TW 전환은 settings.yaml 의 locale 한 줄만 바꾸면 된다."""
import html
from pathlib import Path

import yaml

from .match import Assessment
from .models import Posting
from .targets import Office

LOCALE_DIR = Path(__file__).resolve().parent.parent / "config" / "locales"

VERDICT_ICON = {"fit": "✅", "conditional": "🟡", "blocked": "⛔️", "unknown": "❓", "expired": "⏰"}


def load_locale(name: str) -> dict:
    return yaml.safe_load((LOCALE_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def _esc(s: str) -> str:
    return html.escape(str(s), quote=False)


# 라벨 앞머리 기호로 중요도를 가른다. 막는 것(🔴⛔️)은 위로, 참고(⚪️)는 아래로.
_LABEL_ORDER = {"🔴": 0, "⛔️": 0, "⏰": 1, "🏗": 2, "🔧": 2, "🟡": 3,
                "🌏": 4, "🟢": 5, "🗣": 6, "📍": 7, "⚪️": 8, "⚠️": 9}


def _sort_labels(labels: list[str]) -> list[str]:
    return sorted(labels, key=lambda l: _LABEL_ORDER.get(l[:2].strip(), 5))


def _bullets(items: list[str], limit: int) -> str:
    return "\n".join(f"  • {_esc(x)}" for x in items[:limit])


COUNTRY_FLAG = {"KR": "🇰🇷", "JP": "🇯🇵", "TW": "🇹🇼"}


def _bul(items, limit):
    return "\n".join(f"• {_esc(x)}" for x in items[:limit])


def _tags(p: Posting, office: Office, elig) -> str:
    """해시태그 — 나중에 텔레그램 검색으로 되찾을 수 있게."""
    # 해시태그에 이모지를 쓰면 텔레그램이 태그로 인식하지 않는다
    out = [{"KR": "한국", "JP": "일본", "TW": "대만"}.get(office.country, office.country)]
    t = {"new_grad": "신입공채", "intern": "인턴", "intern_to_fulltime": "전환형인턴",
         "entry_level": "신입", "year_round": "상시채용"}.get(p.track)
    if t:
        out.append(t)
    out.append({"open": "지원가능", "ask": "문의필요",
                "native": "언어장벽", "closed": "지원불가"}[elig.gate])
    for sw in p.software[:3]:
        out.append(sw.replace(" ", ""))
    return " ".join(f"#{x}" for x in dict.fromkeys(out) if x)


def render_posting(p: Posting, office: Office, a: Assessment, L: dict, elig=None) -> str:
    """텔레그램 메시지. 섹션 이모지 + 인용구로 훑기 쉽게 나눈다."""
    from . import eligibility as _el
    elig = elig or _el.judge(p, office.country)

    who = p.company or office.display_name
    where = p.location or office.city or office.country
    track = L["track_label"].get(p.track, p.track)
    flag = COUNTRY_FLAG.get(office.country, "🏛")

    out = [
        f"{flag} <b>{_esc(who)}</b>",
        f"🏛 <b>{_esc(p.title)}</b>",
        "",
        # ── 가장 먼저 보여야 할 것: 애초에 지원이 되는가 ──
        f"{elig.icon} <b>{_esc(elig.label(L.get('_locale', 'ko')))}</b>",
    ]
    if elig.evidence:
        out.append(f"<blockquote>{_esc(elig.evidence)}</blockquote>")
    else:
        out.append(f"<i>{_esc(elig.reason)}</i>")
    if elig.action:
        out.append(f"👉 {_esc(elig.action)}")

    out += ["", f"📍 {_esc(where)}   ·   <code>{_esc(track)}</code>"]
    if p.deadline:
        out.append(f"{'⏰' if a.expired else '🗓'} <b>{L['deadline']} {_esc(p.deadline)}</b>")

    if p.summary:
        out += ["", f"<blockquote>{_esc(p.summary)}</blockquote>"]

    if p.responsibilities:
        out += ["", f"📋 <b>{L['responsibilities']}</b>",
                f"<blockquote>{_bul(p.responsibilities, 10)}</blockquote>"]
    if p.qualifications:
        out += ["", f"✔️ <b>{L['qualifications']}</b>",
                f"<blockquote>{_bul(p.qualifications, 10)}</blockquote>"]
    if p.preferred:
        out += ["", f"➕ <b>{L['preferred']}</b>",
                f"<blockquote>{_bul(p.preferred, 8)}</blockquote>"]
    if p.software:
        out += ["", f"🖥 <b>{L['software']}</b>",
                f"<code>{_esc(' · '.join(p.software[:12]))}</code>"]

    facts = [(L["employment"], p.employment_type), (L["salary"], p.salary),
             (L["process"], p.process), (L["language"], p.language_required)]
    facts = [f"• {k}: {_esc(v)}" for k, v in facts if v]
    if facts:
        out += ["", f"📄 <b>조건</b>", *facts]

    # 판정 근거 — 막는 것만 짧게. 나머지는 웹에서 본다.
    hard = [l for l in a.labels if l[:2].strip() in ("🔴", "⛔️", "⏰", "🏗", "🔧")]
    if hard:
        out += ["", "⚠️ " + "\n⚠️ ".join(_esc(x) for x in hard[:4])]

    if p.notes:
        out += ["", f"❓ <i>{_esc(L['unresolved'])}: {_esc(p.notes)}</i>"]

    out += ["", f'🔗 <a href="{html.escape(p.source_url, quote=True)}">{L["source"]}</a>',
            "", _tags(p, office, elig)]
    return "\n".join(out)


# API 원본 에러를 그대로 텔레그램에 쏟으면 읽을 수가 없다. 사람 말로 바꾼다.
ERROR_PATTERNS = [
    ("PerDay", "일일 한도 소진"),
    ("모든 모델 일일 한도", "모든 모델 일일 한도 소진"),
    ("RESOURCE_EXHAUSTED", "요청 한도 초과"),
    ("UNAVAILABLE", "모델 일시 과부하"),
    ("HTTP 404", "채용 페이지 없음(404)"),
    ("HTTP 403", "접근 차단(403)"),
    ("본문 부족", "JS 렌더링 페이지 — 수동 확인 필요"),
    ("careers_url 없음", "채용 URL 미등록"),
    ("ConnectError", "접속 실패"),
    ("Timeout", "응답 시간 초과"),
]


def humanize_error(raw: str) -> str:
    """'jp-kume: ClientError: 429 RESOURCE_EXHAUSTED. {...}' → 'jp-kume — 요청 한도 초과'"""
    who, _, rest = raw.partition(":")
    for needle, friendly in ERROR_PATTERNS:
        if needle in rest or needle in raw:
            return f"{who.strip()} — {friendly}"
    return f"{who.strip()} — {rest.strip()[:60]}"


def render_summary(checked: int, new: int, errors: list[str], L: dict) -> str:
    msg = L["run_summary"].format(checked=checked, new=new)
    if new == 0:
        msg += f" — {L['no_new']}"
    if errors:
        # 같은 원인끼리 묶는다. 12곳이 같은 이유로 실패하면 12줄이 아니라 1줄이어야 한다.
        counts: dict[str, list[str]] = {}
        for e in errors:
            h = humanize_error(e)
            who, _, reason = h.partition(" — ")
            counts.setdefault(reason or h, []).append(who)
        msg += "\n"
        for reason, whos in sorted(counts.items(), key=lambda kv: -len(kv[1])):
            names = ", ".join(whos[:4]) + (f" 외 {len(whos) - 4}곳" if len(whos) > 4 else "")
            msg += f"\n⚠️ <b>{_esc(reason)}</b> ({len(whos)}) — {_esc(names)}"
    return msg
