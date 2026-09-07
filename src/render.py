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


def render_posting(p: Posting, office: Office, a: Assessment, L: dict) -> str:
    icon = VERDICT_ICON[a.verdict]
    track = L["track_label"].get(p.track, p.track)
    who = p.company or office.display_name
    where = p.location or office.city or office.country

    out = [
        f"{icon} <b>{_esc(p.title)}</b>",
        f"<b>{_esc(who)}</b> · {_esc(where)}",
        f"<code>{_esc(track)}</code>  <b>{_esc(L['verdict'][a.verdict])}</b>",
    ]

    if p.summary:
        out += ["", f"<blockquote>{_esc(p.summary)}</blockquote>"]

    # ── 판정 근거 ── 막는 것부터 위로
    if a.labels:
        out += ["", *[f"{_esc(x)}" for x in _sort_labels(a.labels)]]

    # ── JD 본문 ──
    if p.responsibilities:
        out += ["", f"<b>📋 {L['responsibilities']}</b>", _bullets(p.responsibilities, 6)]
    if p.qualifications:
        out += ["", f"<b>✔️ {L['qualifications']}</b>", _bullets(p.qualifications, 6)]
    if p.preferred:
        out += ["", f"<b>➕ {L['preferred']}</b>", _bullets(p.preferred, 5)]
    if p.software:
        out += ["", f"<b>🖥 {L['software']}</b>  <code>{_esc(' · '.join(p.software[:10]))}</code>"]

    # ── 조건 한 줄 요약 ──
    facts = []
    if p.employment_type:
        facts.append(f"{L['employment']}: {_esc(p.employment_type)}")
    if p.salary:
        facts.append(f"{L['salary']}: {_esc(p.salary)}")
    if p.process:
        facts.append(f"{L['process']}: {_esc(p.process)}")
    if facts:
        out += ["", *[f"· {f}" for f in facts]]

    if p.deadline:
        mark = "⏰" if a.expired else "🗓"
        out += ["", f"{mark} <b>{L['deadline']} {_esc(p.deadline)}</b>"]

    if p.notes:
        out += ["", f"<i>{_esc(L['unresolved'])}: {_esc(p.notes)}</i>"]

    # href 는 속성값이라 따옴표까지 막아야 한다. 안 그러면 텔레그램이 400 으로 통째로 거부한다.
    out += ["", f'<a href="{html.escape(p.source_url, quote=True)}">{L["source"]} →</a>']
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
