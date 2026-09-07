"""마감 판정은 공고가 있는 나라의 시각으로 한다.

이걸 로컬 시각으로 하면 실제로 놓친다.
사용자는 미국 동부(EDT)에 있고 공고는 한국·일본·대만에 있어서 13~14시간 차이가 난다.
EDT 9월 6일 밤 = KST 9월 7일 오전. '오늘 마감' 이라고 알린 공고가 이미 11시간 전에
끝나 있는 일이 실제로 벌어졌다.
"""
from datetime import date, datetime, timedelta, timezone

# 한국·일본 UTC+9, 대만 UTC+8. 셋 다 서머타임이 없어 고정 오프셋으로 충분하다.
TZ = {
    "KR": timezone(timedelta(hours=9)),
    "JP": timezone(timedelta(hours=9)),
    "TW": timezone(timedelta(hours=8)),
}
DEFAULT = TZ["KR"]


def now_in(country: str) -> datetime:
    return datetime.now(TZ.get(country, DEFAULT))


def today_in(country: str) -> date:
    return now_in(country).date()


def days_left(deadline: str | None, country: str) -> int | None:
    """마감까지 남은 일수. 그 나라 시각 기준. 형식이 아니면 None."""
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", deadline or "")
    if not m:
        return None
    try:
        dl = date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return (dl - today_in(country)).days


def is_expired(deadline: str | None, country: str) -> bool:
    d = days_left(deadline, country)
    return d is not None and d < 0
