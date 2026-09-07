"""JS 로 그리는 페이지를 실제 브라우저로 렌더해서 텍스트를 얻는다.

httpx 로 긁으면 본문이 비는 사이트가 많다 —
한국의 `*.recruiter.co.kr` ATS, 대만 사무소 자사 사이트 대부분이 그렇다.
이 모듈은 그런 곳에만 쓰는 폴백이다. 느리고 무거우니 기본 경로로 쓰지 않는다.

playwright 가 없거나 브라우저가 안 깔려 있으면 조용히 None 을 돌려준다 —
렌더링을 못 한다고 파이프라인 전체가 멈추면 안 된다.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_UNAVAILABLE = False  # 한 번 실패하면 매번 재시도하지 않는다


def available() -> bool:
    global _UNAVAILABLE
    if _UNAVAILABLE:
        return False
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        _UNAVAILABLE = True
        return False


def render(url: str, timeout_ms: int = 25_000) -> tuple[str | None, str | None]:
    """(HTML, 에러). 성공하면 렌더가 끝난 뒤의 HTML 을 돌려준다."""
    global _UNAVAILABLE
    if not available():
        return None, "playwright 없음"
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page(
                    locale="ko-KR",
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
                )
                # networkidle 은 광고·소켓이 계속 도는 페이지에서 영원히 안 끝난다.
                # DOM 이 올라온 뒤 잠깐만 기다렸다가, 여유가 있으면 idle 도 노려본다.
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=6_000)
                except Exception:
                    page.wait_for_timeout(2_500)   # idle 이 안 와도 렌더는 대개 끝나 있다
                return page.content(), None
            finally:
                browser.close()
    except Exception as e:
        msg = str(e)
        # 브라우저 자체가 없으면 이후 호출도 전부 실패한다 → 껐다가 다음 실행에 다시 본다
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            _UNAVAILABLE = True
            return None, "브라우저 미설치 (playwright install chromium)"
        return None, f"{type(e).__name__}: {msg[:120]}"
