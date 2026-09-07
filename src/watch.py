"""Tier 1 — 값싼 변경 감지.

채용페이지를 그냥 HTTP 로 긁어서 텍스트 해시만 비교한다. LLM 을 쓰지 않으므로
30분마다 43개를 돌려도 비용이 0이다. 해시가 바뀐 오피스만 Tier 2 로 넘긴다.
"""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx2 as httpx
from selectolax.parser import HTMLParser

from . import render_js
from .targets import Office

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"

# 매 요청마다 달라져서 해시를 흔드는 것들 — 지워야 오탐이 안 난다
NOISE = re.compile(
    r"(csrf[-_]?token|nonce|sessionid|__VIEWSTATE|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?"
    r"|\?v=\d+|&_=\d+)",
    re.I,
)


# 채용 랜딩 페이지에서 "상세 요강"으로 들어가는 링크를 알아보는 말들.
# 랜딩만 읽으면 "채용은 한다"까지만 알고 지원자격·언어조건은 못 본다.
DETAIL_HINT = re.compile(
    r"新卒|中途|募集要項|採用情報|エントリー|インターン|キャリア|"
    r"신입|모집|채용|공고|지원|인턴|"
    r"職缺|徵才|招募|實習|應徵|"
    r"recruit|career|job|position|intern|apply|opening|vacan",
    re.I,
)
# 따라가면 안 되는 것들
SKIP_LINK = re.compile(r"\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?)(?:[?#]|$)|^(mailto|tel|javascript):", re.I)

MAX_FOLLOW = 5        # 랜딩 1개당 따라갈 하위 페이지 수 상한
MAX_IMAGES = 3        # 공고 1건당 모델에 넘길 본문 이미지 수
MIN_IMAGE_BYTES = 40_000   # 로고·아이콘을 거르는 하한
THIN_SHELL = 6_000         # 이보다 얇고 이미지·iframe 도 없으면 JS 껍데기로 본다

# 한국 대기업 공고는 지원자격을 **이미지로** 넣는다. 텍스트만 긁으면 학력·어학·
# 국적 조건을 통째로 못 본다. 현대건설이 그랬다 — iframe 안에 이미지 한 장이 전부였다.
CONTENT_IMG = re.compile(
    r"file\d*\.jobkorea\.co\.kr/Mng/|saramin\.co\.kr/.*(?:recruit|user_files)|"
    r"vmspace\.com/.*upload|/recruit.*\.(?:jpe?g|png)|\.(?:jpe?g|png)$", re.I)
SKIP_IMG = re.compile(r"logo|icon|banner|btn|sprite|ads?\.|facebook|criteo|adnxs|"
                      r"tracking|pixel|blank|spacer", re.I)
MAX_BOARD_FOLLOW = 12  # 잡보드 목록에서 열어볼 개별 공고 수

# 잡보드의 개별 공고 상세 주소 패턴. 목록 페이지만 읽으면 JD 본문이 통째로 빠진다.
BOARD_DETAIL = re.compile(
    r"saramin\.co\.kr/zf_user/jobs/relay/view\?.*rec_idx=|"
    r"jobkorea\.co\.kr/Recruit/GI_Read/|"
    r"518\.com\.tw/job-|104\.com\.tw/job/|"
    r"vmspace\.com/job/job_view\.html", re.I)


# 사람인 데스크톱 상세는 JD 본문을 JS 로 그려서 텍스트가 안 나온다.
# 모바일 페이지는 서버 렌더라 자격요건·우대사항까지 그대로 들어 있다.
SARAMIN_IDX = re.compile(r"rec_idx=(\d+)")


def richest_board_url(url: str) -> str:
    """같은 공고라도 JD 본문이 실제로 들어 있는 주소로 바꿔준다."""
    if "saramin.co.kr" in url:
        m = SARAMIN_IDX.search(url)
        if m:
            return f"https://m.saramin.co.kr/job-search/view?rec_idx={m.group(1)}"
    return url


def find_board_detail_links(html: str, base_url: str) -> list[str]:
    """검색 결과에서 개별 공고 상세 링크만 골라낸다."""
    tree = HTMLParser(html)
    seen: dict[str, None] = {}
    for a in tree.css("a"):
        href = (a.attributes or {}).get("href") or ""
        if not href:
            continue
        url = urljoin(base_url, href).split("#")[0]
        if BOARD_DETAIL.search(url):
            seen.setdefault(richest_board_url(url), None)
        if len(seen) >= MAX_BOARD_FOLLOW:
            break
    return list(seen)


def find_detail_links(html: str, base_url: str) -> list[str]:
    """랜딩 페이지 안에서 채용 상세로 보이는 링크를 고른다. 같은 도메인만."""
    tree = HTMLParser(html)
    host = urlparse(base_url).netloc
    seen: dict[str, None] = {}
    for a in tree.css("a"):
        href = (a.attributes or {}).get("href") or ""
        if not href or SKIP_LINK.search(href):
            continue
        url = urljoin(base_url, href).split("#")[0]
        if urlparse(url).netloc != host or url.rstrip("/") == base_url.rstrip("/"):
            continue
        # 링크 글자 또는 주소 자체에 채용 관련 단어가 있어야 한다
        if DETAIL_HINT.search(a.text() or "") or DETAIL_HINT.search(url):
            seen.setdefault(url, None)
        if len(seen) >= MAX_FOLLOW:
            break
    return list(seen)


def find_content_images(html: str, base_url: str) -> list[str]:
    """공고 본문 이미지 주소를 고른다. 로고·광고·추적 픽셀은 뺀다."""
    tree = HTMLParser(html)
    out: dict[str, None] = {}
    for img in tree.css("img"):
        src = (img.attributes or {}).get("src") or (img.attributes or {}).get("data-src") or ""
        if not src:
            continue
        url = urljoin(base_url, src)
        if not url.startswith("http") or SKIP_IMG.search(url):
            continue
        if CONTENT_IMG.search(url):
            out.setdefault(url, None)
        if len(out) >= MAX_IMAGES * 2:
            break
    return list(out)


def extract_text_with_links(html: str, base_url: str) -> str:
    """잡보드용. 링크 글자 옆에 실제 주소를 붙여서 넘긴다.

    검색 결과 페이지는 공고마다 상세 URL 이 따로 있는데, 텍스트만 뽑으면 그게 사라져서
    모델이 출처로 검색페이지 주소밖에 쓸 수 없게 된다."""
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, svg"):
        tag.decompose()
    for a in tree.css("a"):
        href = (a.attributes or {}).get("href") or ""
        if not href or SKIP_LINK.search(href):
            continue
        label = " ".join((a.text() or "").split())
        if len(label) < 4:
            continue
        a.replace_with(f"{label} <{urljoin(base_url, href).split('#')[0]}> ")
    body = tree.body or tree.root
    text = body.text(separator=" ") if body else ""
    return " ".join(NOISE.sub("", text).split())


def extract_text(html: str) -> str:
    """본문 텍스트만 남긴다. 스크립트·스타일과 시간표시 노이즈는 버린다."""
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, svg"):
        tag.decompose()
    body = tree.body or tree.root
    text = body.text(separator=" ") if body else ""
    text = NOISE.sub("", text)
    return " ".join(text.split())


# JobKorea 는 공고 본문을 iframe 에 넣는다. 본체만 읽으면 25자짜리 껍데기를 읽게 된다.
IFRAME_BODY = re.compile(r"GI_Read_Comt_Ifrm|user_content|jobDetail", re.I)


def find_body_iframes(html: str, base_url: str) -> list[str]:
    tree = HTMLParser(html)
    out: dict[str, None] = {}
    for f in tree.css("iframe"):
        src = (f.attributes or {}).get("src") or ""
        if src and IFRAME_BODY.search(src):
            out.setdefault(urljoin(base_url, src), None)
    return list(out)


async def fetch_one(
    client: httpx.AsyncClient, office: Office, follow: bool = True
) -> tuple[Office, str | None, str | None]:
    """(office, 추출한 텍스트, 에러) — 에러가 있으면 텍스트는 None.

    랜딩 페이지만으로는 지원자격·언어조건을 알 수 없는 경우가 많아서,
    채용 상세로 보이는 하위 링크를 한 단계만 따라가 본문을 합친다."""
    url = office.careers_url
    if not url:
        return office, None, "careers_url 없음"
    try:
        r = await client.get(url, follow_redirects=True)
        if r.status_code >= 400:
            return office, None, f"HTTP {r.status_code}"
        is_board = office.tier == "job_board"
        html = r.text
        text = (extract_text_with_links(html, str(r.url)) if is_board
                else extract_text(html))

        # 본문이 비거나 얄팍하면 JS 로 그리는 페이지다. 브라우저로 한 번 더 읽는다.
        # (한국 *.recruiter.co.kr ATS, 대만 사무소 자사 사이트, 그리고 공고 본문을
        #  iframe·이미지로 넣는 JobKorea 대기업 공고가 여기 해당한다)
        thin = len(text) < 200
        maybe_shell = (len(text) < THIN_SHELL
                       and not find_content_images(html, str(r.url))
                       and not find_body_iframes(html, str(r.url)))
        rendered = None
        if thin or maybe_shell:
            rendered, rerr = await asyncio.to_thread(render_js.render, str(r.url))
            if rendered:
                html = rendered
                text = (extract_text_with_links(html, str(r.url)) if is_board
                        else extract_text(html))
            if len(text) < 200:
                return office, None, f"본문 부족(JS 렌더링{'' if rendered else ' 실패: ' + (rerr or '')})"

        images: list[str] = list(find_content_images(html, str(r.url)))

        # 이 페이지 자체가 공고일 수도 있다. 본문 iframe 이 있으면 그것도 읽는다
        # (JobKorea 는 공고 본문을 iframe 에 넣어서, 본체만 읽으면 껍데기를 읽게 된다)
        for fr in find_body_iframes(html, str(r.url))[:2]:
            try:
                fr_r = await client.get(fr, follow_redirects=True)
                fr_text = extract_text(fr_r.text)
                images.extend(find_content_images(fr_r.text, fr))
                if len(fr_text) > 60:
                    text += f"\n\n[PAGE] {fr}\n{fr_text}"
            except Exception:
                pass

        if follow:
            parts = [f"[PAGE] {url}\n{text}"]
            # 잡보드는 목록에 JD 가 없다. 개별 공고를 열어야 업무·자격요건이 나온다.
            links = (find_board_detail_links(html, str(r.url)) if is_board
                     else find_detail_links(html, str(r.url)))
            for link in links:
                try:
                    sub = await client.get(link, follow_redirects=True)
                    if sub.status_code >= 400:
                        continue
                    sub_html = sub.text
                    sub_text = extract_text(sub_html)
                    # 본문이 iframe 에 있으면 그것까지 읽는다
                    for fr in find_body_iframes(sub_html, link)[:2]:
                        try:
                            fr_r = await client.get(fr, follow_redirects=True)
                            fr_text = extract_text(fr_r.text)
                            if len(fr_text) > len(sub_text):
                                sub_text = fr_text
                            images.extend(find_content_images(fr_r.text, fr))
                        except Exception:
                            pass
                    images.extend(find_content_images(sub_html, link))
                    if len(sub_text) >= 150:
                        parts.append(f"[PAGE] {link}\n{sub_text}")
                except Exception:
                    continue  # 하위 페이지 실패는 무시 — 랜딩만으로도 진행한다
            text = "\n\n".join(parts)
        # 이미지 주소를 본문 끝에 실어 보낸다 (추출기가 비전으로 읽는다)
        if images:
            uniq = list(dict.fromkeys(images))[:MAX_IMAGES]
            text += "\n\n[IMAGES]\n" + "\n".join(uniq)
        return office, text, None
    except Exception as e:  # 네트워크/타임아웃/파싱 전부
        return office, None, f"{type(e).__name__}: {e}"


async def watch(offices: list[Office], timeout: int, max_parallel: int):
    """전 오피스를 병렬로 긁는다. 반환: [(office, text, error), ...]"""
    sem = asyncio.Semaphore(max_parallel)

    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "ko,ja,zh-TW,en"}
    ) as client:

        async def guarded(o: Office):
            async with sem:
                return await fetch_one(client, o)

        return await asyncio.gather(*(guarded(o) for o in offices))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
