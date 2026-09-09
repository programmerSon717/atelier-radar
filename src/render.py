"""텔레그램 메시지 만들기.

**웹에 있는 것을, 웹과 같은 순서로, 웹과 같은 말로 보여준다.**
  · 화면 문구 → config/locales/<lang>.yaml 의 web: 절. site/ui.js 와 같은 파일에서 온다.
  · 공고 내용 → 저장분의 _i18n 번역본 (tools/translate_postings.py · src/i18n.py).
번역이 아직 없는 자리만 원문으로 떨어진다 (사이트의 F() 와 같은 규칙).

예전에는 봇이 원문 필드를 그대로 실어서 한국어·일본어 공고가 그대로 나갔고,
섹션 제목도 여기 한국어로 박혀 있었다. 그래서 웹과 봇이 다른 물건이었다.
"""
import html
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from . import clock
from .match import Assessment
from .models import Posting
from .targets import Office

LOCALE_DIR = Path(__file__).resolve().parent.parent / "config" / "locales"

VERDICT_ICON = {"fit": "✅", "conditional": "🟡", "blocked": "⛔️", "unknown": "❓", "expired": "⏰"}
COUNTRY_FLAG = {"KR": "🇰🇷", "JP": "🇯🇵", "TW": "🇹🇼"}
FIT_ICON = {"recommend": "👍", "neutral": "➖", "avoid": "👎"}
# 사이트의 TRACK_KEY 와 같은 표 (site/app.js)
TRACK_KEY = {"new_grad": "track_new_grad", "intern": "track_intern",
             "intern_to_fulltime": "track_intern_ft", "entry_level": "track_new_grad",
             "year_round": "track_year_round", "other": "tier_other"}
SOURCE_KEY = {"사람인 기업정보": "src_saramin"}


def load_locale(name: str) -> dict:
    return yaml.safe_load((LOCALE_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=False)


def T(L: dict, key: str, **vars: Any) -> str:
    """화면 문구. 사이트의 T() 와 같은 자리를 본다."""
    v = (L.get("web") or {}).get(key, key)
    for k, x in vars.items():
        v = v.replace("{" + k + "}", str(x))
    # 웹 문구에는 <b> 가 섞여 있다 (a_korean 등). 텔레그램도 <b> 를 그대로 쓴다.
    return v


def _val(tr: Optional[dict], src: dict, field: str):
    """번역본에 값이 있으면 그것, 없으면 원문. 사이트의 F() 와 같은 규칙."""
    v = (tr or {}).get(field)
    if isinstance(v, list):
        if v:
            return v
    elif v not in (None, ""):
        return v
    return src.get(field)


# ── 조각들 ──────────────────────────────────────────────
def _bul(items, limit: int) -> str:
    return "\n".join(f"• {_esc(x)}" for x in (items or [])[:limit])


def _block(title: str, items, limit: int = 12) -> Optional[str]:
    if not items:
        return None
    return f"{title}\n<blockquote>{_bul(items, limit)}</blockquote>"


def pay_value(raw: Any, lang: str) -> str:
    """'8,460만원' 을 중문 화면에 그대로 두면 읽을 수 없다. site/app.js payValue 와 같은 규칙."""
    s = str(raw or "")
    if lang == "ko":
        return s
    m = re.fullmatch(r"([\d,]+)\s*만원", s.strip())
    if m:
        won = int(m.group(1).replace(",", "")) * 10000
        return f"KRW {won:,}" if lang == "en" else f"{m.group(1)}萬韓元"
    m = re.fullmatch(r"([\d,]+)\s*万円", s.strip())
    if m:
        yen = int(m.group(1).replace(",", "")) * 10000
        return f"JPY {yen:,}" if lang == "en" else f"{m.group(1)}萬日圓"
    return s


def _source_name(L: dict, v: Any) -> str:
    k = SOURCE_KEY.get(str(v or ""))
    return T(L, k) if k else str(v or "")


def _track_label(L: dict, track: Optional[str]) -> str:
    return T(L, TRACK_KEY.get(track or "", "tier_other"))


def _tags(L: dict, p: Posting, country: str, gate: str,
          software: list | None = None) -> str:
    """해시태그 — 나중에 텔레그램 검색으로 되찾을 수 있게. 이모지는 태그로 인식되지 않는다."""
    b = L.get("bot") or {}
    out = [(b.get("tag_country") or {}).get(country, country)]
    t = (b.get("tag_track") or {}).get(p.track or "")
    if t:
        out.append(t)
    # 게이트가 늘어날 때 여기를 빠뜨리면 파이프라인이 통째로 죽는다. get 으로 받는다.
    out.append((b.get("tag_gate") or {}).get(gate) or (b.get("tag_gate") or {}).get("unknown", ""))
    for sw in (software if software is not None else (p.software or []))[:3]:
        out.append(sw.replace(" ", ""))
    return " ".join(f"#{x}" for x in dict.fromkeys(out) if x)


def _urgency(L: dict, p: Posting, country: str) -> Optional[str]:
    """마감이 코앞이면 맨 위에 띄운다. 내일 마감인 공고를 목록 중간에서 발견하면 늦는다.

    반드시 **공고가 있는 나라 시각**으로 센다 (사이트도 같다). 미국에서 보면 하루 어긋난다."""
    d = clock.days_left(p.deadline, country)
    if d is None or d < 0 or d > 3:
        return None
    return f"🚨 <b>{T(L, 'today_due') if d == 0 else T(L, 'due_in', n=d)}</b>"


def render_posting(p: Posting, office: Office, a: Assessment, L: dict,
                   elig=None, kit=None, pay=None, fit=None,
                   tr: Optional[dict] = None, lang: str = "zh_TW",
                   country: Optional[str] = None) -> str:
    """사이트의 row() 와 같은 것을, 같은 순서로."""
    from . import eligibility as _el
    from . import i18n as _i18n

    pc = country or office.country
    elig = elig or _el.judge(p, pc)
    fit_grade, fit_why = fit if fit else (None, [])
    kitd = _i18n.kit_dict(kit)
    src = _i18n.display_source(p, a, elig, fit_why, pay, kitd)
    F = lambda f: _val(tr, src, f)                                    # noqa: E731

    dl = clock.days_left(p.deadline, pc)
    flag = COUNTRY_FLAG.get(pc, "🏛")
    track = _track_label(L, p.track)

    blocks: list[str] = []

    # ── 머리: 게이트 · 추천도 · 제목 · 회사 (사이트의 .rtop) ──
    head = [f"{elig.icon} <b>{_esc(F('gate_label') or T(L, 'g_' + elig.gate))}</b>"]
    if fit_grade:
        why = " · ".join((F("fit_why") or [])[:3])
        head.append(f"{FIT_ICON.get(fit_grade, '➖')} <b>{_esc(T(L, 'fit_' + fit_grade))}</b>"
                    + (f" <i>— {_esc(why)}</i>" if why else ""))
    head.append(f"🏛 <b>{_esc(F('title'))}</b>")
    # 국기는 메타 줄에만 둔다 (사이트도 .rtop 에는 국기가 없다)
    head.append(f"<b>{_esc(F('company') or office.display_name)}</b>")
    blocks.append("\n".join(head))

    urgent = _urgency(L, p, pc)
    if urgent:
        blocks.append(urgent)

    # ── 메타 한 줄 (사이트의 .meta) ──
    et = F("employment_type")
    # 고용형태가 트랙과 같은 말이면 두 번 쓰지 않는다 ("實習 · 實習")
    if et and (track and track in str(et) or re.fullmatch(r"intern(ship)?|인턴|實習",
                                                          str(p.employment_type or "").strip(), re.I)):
        et = None
    meta = [f"{flag} {_esc(F('location') or office.display_name)}", f"<code>{_esc(track)}</code>"]
    if et:
        meta.append(_esc(et))
    if p.deadline:
        d_txt = (f"{T(L, 'expired') if a.expired else T(L, 'deadline')} "
                 f"{_esc(F('deadline_text') or p.deadline)}")
        if dl is not None and 0 <= dl <= 30:
            d_txt += f" (D-{dl})"
        meta.append(f"<b>{d_txt}</b>")
    blocks.append("📍 " + "   ·   ".join(meta))

    # ── 왜 이 판정인가 (사이트의 .why / .act) ──
    why_line = F("gate_evidence") or F("gate_reason")
    if why_line:
        blocks.append(f"<b>{_esc(F('gate_label') or '')}</b>\n<blockquote>{_esc(why_line)}</blockquote>")
    if F("gate_action"):
        blocks.append(f"👉 {_esc(F('gate_action'))}")
    if F("summary"):
        blocks.append(f"<blockquote>{_esc(F('summary'))}</blockquote>")

    # ── 본문 (사이트의 .jd — 순서까지 같다) ──
    jd: list[Optional[str]] = [
        _block(f"📋 <b>{T(L, 'resp')}</b>", F("responsibilities")),
        _block(f"✔️ <b>{T(L, 'qual')}</b>", F("qualifications")),
        _block(f"➕ <b>{T(L, 'pref')}</b>", F("preferred")),
    ]
    software = F("software") or p.software
    if software:
        jd.append(f"🖥 <b>{T(L, 'soft')}</b>\n<code>{_esc(' · '.join(software[:12]))}</code>")

    facts = [(T(L, "cond_employ"), F("employment_type")),
             (T(L, "cond_process"), F("process")),
             (T(L, "cond_lang"), F("language_required"))]
    facts = [f"• {k}: {_esc(v)}" for k, v in facts if v]
    if facts:
        jd.append(f"📄 <b>{T(L, 'cond')}</b>\n" + "\n".join(facts))
    if F("notes"):
        jd.append(f"❓ <b>{T(L, 'unknown_h')}</b>\n<i>{_esc(F('notes'))}</i>")

    # 연락처 — 문의하라고만 하고 어디로 할지 안 주면 아무것도 못 한다
    contacts = []
    if p.contact_email:
        contacts.append(f"✉️ <code>{_esc(p.contact_email)}</code>")
    if p.contact_phone:
        contacts.append(f"☎️ <code>{_esc(p.contact_phone)}</code>")
    if F("apply_how"):
        contacts.append(f"📮 {_esc(F('apply_how'))}")
    if contacts:
        jd.append(f"📇 <b>{T(L, 'contact_h')}</b>\n" + "\n".join(contacts))

    jd.append(_block(f"🏗 <b>{T(L, 'projects')}</b>", F("firm_projects"), 6))

    # 연봉 — 공고값과 참고치를 반드시 구분한다 (사이트와 같은 표기)
    if pay:
        lines = []
        if pay.get("stated"):
            lines.append(f"• {T(L, 'pay_stated')}: <b>{_esc(F('pay_stated') or pay['stated'])}</b>")
        elif p.salary:
            lines.append(f"• {T(L, 'pay_stated')}: {_esc(F('salary') or p.salary)} {T(L, 'pay_noamt')}")
        c = pay.get("company_avg")
        if c:
            lines.append(f"• [{T(L, 'pay_ref')}] {T(L, 'pay_avg')} "
                         f"<b>{_esc(pay_value(c.get('average'), lang))}</b>")
            lines.append(f"  <i>{_esc(F('pay_note') or c.get('basis') or '')} · "
                         f"{T(L, 'pay_src')}: {_esc(_source_name(L, c.get('source')))}</i>")
        if not lines:
            lines.append(f"• <i>{T(L, 'pay_none')}</i>")
        jd.append(f"💰 <b>{T(L, 'pay')}</b>\n" + "\n".join(lines))

    # 판정 근거 — 뭐가 막고 뭐가 되는지 제목으로 가른다
    jd += [
        _block(f"⛔ <b>{T(L, 'blockers')}</b>", F("blockers_desc"), 5),
        _block(f"🔧 <b>{T(L, 'softb')}</b>", F("soft_desc"), 4),
        _block(f"✔️ <b>{T(L, 'met')}</b>", F("met"), 4),
        _block(f"❔ <b>{T(L, 'unknowns')}</b>", F("unknowns"), 4),
    ]
    jd = [x for x in jd if x]
    if jd:
        blocks += jd
    else:
        blocks.append(f"<i>{T(L, 'thin')}</i>")

    # ── 문의 메일 초안 ── 읽는 말로 보여주고, 보낼 원문을 따로 붙인다 (사이트와 같다)
    if kitd:
        subj = F("mail_subject") or kitd.get("subject")
        body = F("mail_body") or kitd.get("body")
        blocks.append(f"📨 <b>{T(L, 'mail_h')}</b>\n"
                      f"<b>{T(L, 'mail_subject')}:</b> {_esc(subj)}\n"
                      f"<blockquote>{_esc(body)}</blockquote>")
        if body != kitd.get("body"):
            blocks.append(f"<i>{T(L, 'mail_send_note')}</i>\n"
                          f"<blockquote expandable>{_esc(kitd.get('body'))}</blockquote>")
        blocks.append(_block(f"🪝 <b>{T(L, 'hooks')}</b>", F("mail_hooks"), 4) or "")
        blocks.append(_block(f"❓ <b>{T(L, 'asks')}</b>", F("mail_asks"), 4) or "")

    blocks.append(f'🔗 <a href="{html.escape(p.source_url, quote=True)}">{T(L, "source")}</a>')
    blocks.append(_tags(L, p, pc, elig.gate, software))
    return "\n\n".join(b for b in blocks if b)


# API 원본 에러를 그대로 텔레그램에 쏟으면 읽을 수가 없다. 사람 말로 바꾼다.
ERROR_PATTERNS = [
    ("PerDay", "quota_day"),
    ("모든 모델 일일 한도", "quota_all"),
    ("RESOURCE_EXHAUSTED", "quota_rate"),
    ("UNAVAILABLE", "overload"),
    ("HTTP 404", "http404"),
    ("HTTP 403", "http403"),
    ("본문 부족", "js_page"),
    ("careers_url 없음", "no_url"),
    ("ConnectError", "connect"),
    ("Timeout", "timeout"),
]


def humanize_error(raw: str, L: dict) -> str:
    """'jp-kume: ClientError: 429 RESOURCE_EXHAUSTED. {...}' → 'jp-kume — 超出請求額度'"""
    errs = (L.get("bot") or {}).get("errors") or {}
    who, _, rest = raw.partition(":")
    for needle, key in ERROR_PATTERNS:
        if needle in rest or needle in raw:
            return f"{who.strip()} — {errs.get(key, key)}"
    return f"{who.strip()} — {rest.strip()[:60]}"


def render_summary(checked: int, new: int, errors: list[str], L: dict) -> str:
    msg = L["run_summary"].format(checked=checked, new=new)
    if new == 0:
        msg += f" — {L['no_new']}"
    if errors:
        # 같은 원인끼리 묶는다. 12곳이 같은 이유로 실패하면 12줄이 아니라 1줄이어야 한다.
        counts: dict[str, list[str]] = {}
        for e in errors:
            h = humanize_error(e, L)
            who, _, reason = h.partition(" — ")
            counts.setdefault(reason or h, []).append(who)
        more = (L.get("bot") or {}).get("more_offices", "+{n}")
        msg += "\n"
        for reason, whos in sorted(counts.items(), key=lambda kv: -len(kv[1])):
            names = ", ".join(whos[:4])
            if len(whos) > 4:
                names += " " + more.replace("{n}", str(len(whos) - 4))
            msg += f"\n⚠️ <b>{_esc(reason)}</b> ({len(whos)}) — {_esc(names)}"
    return msg
