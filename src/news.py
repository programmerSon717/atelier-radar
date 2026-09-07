"""사무소 프로젝트가 채용페이지에 없을 때, 뉴스에서 근거를 찾아온다.

메일에 "프로젝트 목록이 기재되어 있지 않으나" 같은 말을 쓸 수는 없다.
모르면 가만히 있는 게 아니라 밖에서 찾아와야 한다. 여기서 찾은 것도
'확인된 사실' 로만 쓴다 — 제목에 적힌 것 이상으로 부풀리지 않는다.

Google 뉴스 RSS 는 공개 피드다. 로그인·차단을 우회하지 않는다.
"""
import re
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx

FEED = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"

# 나라별 (hl, gl, lang) 과 검색어에 덧붙일 분야어
LOCALE = {
    "KR": ("ko", "KR", "ko", "건축"),
    "JP": ("ja", "JP", "ja", "建築"),
    "TW": ("zh-TW", "TW", "zh-Hant", "建築"),
}

# 채용·주가·부고처럼 메일에 쓸 수 없는 기사
NOISE = re.compile(r"채용|공채|모집|주가|증시|배당|부고|인사\s*발령|소송|횡령|"
                   r"求人|採用|株価|"
                   r"徵才|招募|股價|"
                   r"hiring|recruit|stock", re.I)


def _clean(t: str) -> str:
    # Google 뉴스 제목은 "제목 - 매체명" 형식이다. 매체명은 근거로 남긴다.
    return re.sub(r"\s+", " ", t).strip()


def headlines(firm: str, country: str, limit: int = 5, timeout: float = 10.0
              ) -> list[dict[str, str]]:
    """[{title, source, date, url}]. 실패하면 빈 리스트 — 메일 생성을 막지 않는다."""
    hl, gl, lang, field = LOCALE.get(country, ("en", "US", "en", "architecture"))
    q = quote_plus(f'"{firm}" {field}')
    url = FEED.format(q=q, hl=hl, gl=gl, lang=lang)
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "atelier-radar/1.0"})
        r.raise_for_status()
        root = ElementTree.fromstring(r.content)
    except Exception:
        return []

    out: list[dict[str, str]] = []
    for item in root.iter("item"):
        title = _clean((item.findtext("title") or ""))
        if not title or NOISE.search(title):
            continue
        src = (item.findtext("source") or "").strip()
        out.append({
            "title": title,
            "source": src,
            "date": (item.findtext("pubDate") or "")[:16].strip(),
            "url": (item.findtext("link") or "").strip(),
        })
        if len(out) >= limit:
            break
    return out
