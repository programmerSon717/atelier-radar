"""추적 범위는 한국·일본·대만 셋뿐이다.

坂茂처럼 도쿄 사무소를 추적하는데 뉴욕·파리 자리까지 같이 올라오는 경우가 있어서,
공고의 근무지를 보고 범위 밖이면 버린다. 사무소 국적이 아니라 **공고의 근무지**가 기준이다.
"""
import re

COUNTRY_PATTERNS = {
    "KR": re.compile(r"서울|한국|대한민국|경기|부산|인천|성수|강남|seoul|korea", re.I),
    "JP": re.compile(r"東京|大阪|京都|名古屋|横浜|日本|tokyo|osaka|kyoto|japan|nagoya", re.I),
    "TW": re.compile(r"台北|臺北|台中|台灣|臺灣|高雄|新竹|taipei|taiwan|taichung|kaohsiung", re.I),
}

# 명확히 범위 밖인 곳들. 여기 걸리면 국내 표시가 없는 한 버린다.
OUT_OF_SCOPE = re.compile(
    r"new york|newyork|\bNYC\b|paris|london|shanghai|beijing|上海|北京|巴黎|倫敦|"
    r"singapore|hong ?kong|香港|新加坡|berlin|milan|los angeles|\bLA\b|dubai|sydney|"
    r"amsterdam|copenhagen|barcelona|madrid|toronto|vancouver|melbourne|bangkok",
    re.I,
)


def posting_location_text(posting) -> str:
    """근무지 판단에 쓸 텍스트. 근무지 필드가 비면 제목까지 본다
    (坂茂처럼 제목에 'Internship at New York Office' 로 박혀 있는 경우가 있다)."""
    return " ".join(filter(None, [posting.location, posting.title]))


def in_scope(posting, office_country: str) -> tuple[bool, str]:
    """(범위 안인지, 이유). 판단 근거가 전혀 없으면 사무소 국가를 믿고 통과시킨다."""
    text = posting_location_text(posting)
    if not text.strip():
        return True, ""

    # 한/일/대 중 하나가 명시돼 있으면 통과
    for code, pat in COUNTRY_PATTERNS.items():
        if pat.search(text):
            return True, ""

    m = OUT_OF_SCOPE.search(text)
    if m:
        return False, f"근무지 범위 밖: {m.group(0)}"

    # 아무 지역 표시가 없으면 사무소가 있는 나라의 자리로 본다
    return True, ""
