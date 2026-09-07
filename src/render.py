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
    # 게이트가 늘어날 때 여기를 빠뜨리면 파이프라인이 통째로 죽는다. get 으로 받는다.
    out.append({"open": "지원가능", "ask": "문의필요", "native": "언어장벽",
                "domestic": "국내대학전형", "closed": "지원불가"}.get(elig.gate, "확인필요"))
    for sw in p.software[:3]:
        out.append(sw.replace(" ", ""))
    return " ".join(f"#{x}" for x in dict.fromkeys(out) if x)


def _urgency(p: Posting, country: str) -> str | None:
    """마감이 코앞이면 맨 위에 띄운다. 내일 마감인 공고를 목록 중간에서 발견하면 늦는다.

    반드시 **공고가 있는 나라 시각**으로 센다. 미국에서 보면 하루 어긋난다."""
    from . import clock
    d = clock.days_left(p.deadline, country)
    if d is None or d < 0:
        return None
    if d == 0:
        return "🚨 <b>오늘 마감</b> — 오늘 안에 접수해야 한다"
    if d <= 3:
        return f"🚨 <b>D-{d} 마감 임박</b>"
    if d <= 7:
        return f"⏳ <b>D-{d}</b>"
    return None


FIT_ICON = {"recommend": "👍", "neutral": "➖", "avoid": "👎"}


def render_posting(p: Posting, office: Office, a: Assessment, L: dict,
                   elig=None, kit=None, pay=None, fit=None) -> str:
    """텔레그램 메시지. 섹션 이모지 + 인용구로 훑기 쉽게 나눈다."""
    from . import eligibility as _el
    elig = elig or _el.judge(p, office.country)

    who = p.company or office.display_name
    where = p.location or office.city or office.country
    track = L["track_label"].get(p.track, p.track)
    flag = COUNTRY_FLAG.get(office.country, "🏛")

    urgent = _urgency(p, office.country)
    out = ([urgent, ""] if urgent else []) + [
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

    # ── 추천도 ── 지원이 되느냐 다음으로 궁금한 건 "여기 갈 만한가" 다
    if fit:
        grade, reasons = fit
        out += ["", f"{FIT_ICON.get(grade, '➖')} <b>{_esc(L['fit'][grade])}</b>"]
        if reasons:
            out.append(f"<blockquote>{_bul(reasons, 3)}</blockquote>")

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

    facts = [(L["employment"], p.employment_type),
             (L["process"], p.process), (L["language"], p.language_required)]
    facts = [f"• {k}: {_esc(v)}" for k, v in facts if v]
    if facts:
        out += ["", f"📄 <b>조건</b>", *facts]

    # ── 연봉 ── 공고값과 업계 참고치를 반드시 구분해서 보여준다
    if pay:
        lines = []
        if pay.get("stated"):
            lines.append(f"• 공고 명시: <b>{_esc(pay['stated'])}</b>")
        elif p.salary:
            lines.append(f"• 공고 명시: {_esc(p.salary)} (금액 없음)")
        b = pay.get("benchmark")
        if b:
            lines.append(f"• 업계 참고: <b>{_esc(b['range'])}</b> (신입)")
            if b.get("note"):
                lines.append(f"  <i>{_esc(b['note'])}</i>")
            lines.append(f"  <i>※ {_esc(b['disclaimer'])}</i>")
        if lines:
            out += ["", "💰 <b>연봉</b>", *lines]

    # 판정 근거는 색깔 공이 아니라 제목으로 나눈다. 뭐가 막고 뭐가 되는지가 바로 보인다.
    if a.blockers_desc:
        out += ["", "⛔ <b>걸리는 조건</b>",
                f"<blockquote>{_bul(a.blockers_desc, 5)}</blockquote>"]
    if a.soft_desc:
        out += ["", "🔧 <b>준비하면 넘는 조건</b>",
                f"<blockquote>{_bul(a.soft_desc, 4)}</blockquote>"]
    if a.met:
        out += ["", "✔️ <b>충족하는 조건</b>",
                f"<blockquote>{_bul(a.met, 4)}</blockquote>"]
    if a.unknowns:
        out += ["", "❔ <b>공고에 없어 확인이 필요한 것</b>",
                f"<blockquote>{_bul(a.unknowns, 4)}</blockquote>"]

    if p.notes:
        out += ["", f"❓ <i>{_esc(L['unresolved'])}: {_esc(p.notes)}</i>"]

    # ── 연락처 ── 문의하라고만 하고 어디로 할지 안 주면 아무것도 못 한다
    contacts = []
    if p.contact_email:
        contacts.append(f"✉️ <code>{_esc(p.contact_email)}</code>")
    if p.contact_phone:
        contacts.append(f"☎️ <code>{_esc(p.contact_phone)}</code>")
    if p.apply_how:
        contacts.append(f"📮 {_esc(p.apply_how)}")
    if contacts:
        out += ["", "📇 <b>연락처 · 지원 방법</b>", *contacts]

    if p.firm_projects:
        out += ["", "🏗 <b>이 사무소 프로젝트</b>",
                f"<blockquote>{_bul(p.firm_projects, 6)}</blockquote>"]

    # ── 바로 보낼 수 있는 문의 메일 ──
    if kit is not None:
        out += ["", "📨 <b>문의 메일 초안</b>",
                f"<b>제목:</b> {_esc(kit.subject)}",
                f"<blockquote>{_esc(kit.body)}</blockquote>"]
        if kit.hooks:
            out += ["🪝 <b>엮을 거리</b>", f"<blockquote>{_bul(kit.hooks, 4)}</blockquote>"]
        if kit.ask_points:
            out += ["❓ <b>꼭 물어볼 것</b>", f"<blockquote>{_bul(kit.ask_points, 4)}</blockquote>"]

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
