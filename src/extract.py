"""Gemini 추출기 — 채용페이지 원문을 읽고 공고를 구조화한다.

검색 그라운딩은 쓰지 않는다 (무료 티어에 할당량이 없다). 대신 watch.py 가 이미
가져온 페이지 텍스트를 그대로 넘긴다. 검색 결과를 요약하는 것보다 원문을 읽는 쪽이
지어낼 여지도 적다.
"""
import asyncio
import os
import random
import time
from datetime import date
from typing import Any, Optional

from google import genai
from google.genai import types

from .models import OfficeReport
from .targets import Office

MAX_PAGE_CHARS = 60_000  # 전체 예산. 페이지가 여러 개면 나눠 쓴다.


def budget_pages(text: str, limit: int = MAX_PAGE_CHARS) -> str:
    """`[PAGE] url` 로 이어붙인 본문을 페이지 수만큼 나눠서 자른다.

    통째로 앞에서 자르면 잡보드처럼 목록이 긴 경우 뒤쪽 상세 공고가 전부 날아간다.
    페이지마다 몫을 주고, 짧은 페이지가 남긴 몫은 긴 페이지가 가져간다."""
    if len(text) <= limit:
        return text
    parts = text.split("\n\n[PAGE] ")
    if len(parts) == 1:
        return text[:limit]
    parts = [parts[0]] + ["[PAGE] " + p for p in parts[1:]]

    share = limit // len(parts)
    spare = sum(share - len(p) for p in parts if len(p) < share)
    long_n = sum(1 for p in parts if len(p) > share) or 1
    bonus = spare // long_n
    return "\n\n".join(p if len(p) <= share else p[:share + bonus] for p in parts)

# 모델이 생성하는 문장의 언어. UI 문구는 config/locales/ 가 따로 담당한다.
OUT_LANG = {
    "ko": "한국어",
    "zh_TW": "번체 중문(繁體中文) — 대만에서 쓰는 자연스러운 표현으로. 중국 대륙식 어휘 금지",
}

SYSTEM = """\
너는 건축설계사무소 채용 페이지를 읽고 공고를 정리하는 추출기다.

절대 규칙 — 어기면 결과는 폐기된다:
1. **아래 제공된 페이지 텍스트에 실제로 있는 내용만** 보고한다.
   네가 알고 있는 회사 지식이나 추측으로 공고를 만들지 마라.
2. 페이지 텍스트는 `[PAGE] <url>` 로 구분된 여러 페이지가 이어붙어 있을 수 있다.
   각 posting 의 source_url 에는 **그 공고가 실제로 실려 있던 [PAGE] 의 url** 을 적어라.
3. 페이지에 안 적힌 항목은 null 로 두고, 무엇을 못 밝혔는지 unresolved 에 적는다.
   "아마 일본어가 필요할 것이다" 같은 추론을 language_required 에 쓰지 마라.
4. confidence: 회사 공식 채용페이지 원문이면 confirmed, 그 외 unverified.
5. 채용 공고가 없으면 postings 를 빈 배열로 둔다. 빈 결과는 정상이다.
   "채용 안내" 같은 일반 문구만 있고 실제 공고가 없으면 postings 는 비운다.
6. requires_japanese / requires_korean 은 페이지에 언어 조건이 명시된 경우만 채운다.
   영어로 대체 가능하면 false. 언급이 없으면 null.

## JD 본문 채우기
responsibilities / qualifications / preferred / software / salary / employment_type / process
는 **공고에 적혀 있으면 반드시 채운다.** 요약만 하고 넘어가지 마라.
- 목록 항목은 원문을 압축해서 한 줄씩. 미사여구는 빼고 실제 내용만.
- 페이지에 없는 항목은 빈 배열이나 null 로 둔다. 지어내지 마라.
- software 는 공고에 실제로 이름이 나온 것만 (Revit, Rhino, AutoCAD, SketchUp, 3ds Max 등).

language_required 에는 페이지 원문 표현을 그대로 옮겨라 (예: "日本語能力試験N2以上").

## 출력 언어
summary, notes, unresolved 는 **{out_lang}** 로 써라.
단 title 과 language_required 는 원문 언어 그대로 둔다 — 번역하면 검증이 불가능해진다.
"""

USER = """\
## 사무소
- id: {office_id}
- 이름: {name}
- 국가/도시: {country} / {city}

## 페이지
- page_url: {url}
- 오늘 날짜: {today}

## 참고 (후보자)
대만 국적 / 미국 대학원 M.Arch 2027년 5월 졸업 예정 / 정규직 경력 0년
영어 능통, 중국어 네이티브, 한국어 초급, **일본어 없음**

## 페이지 텍스트
```
{page_text}
```

위 텍스트에서 신입공채·인턴·전환형 인턴·상시채용 공고를 찾아 정리해라.
언어 요건과 졸업연도 조건을 특히 빠뜨리지 마라. 없으면 없다고 적어라.
{board_note}
"""

BOARD_NOTE = """
## ★ 이 페이지는 채용 사이트의 검색 결과다 (여러 회사가 섞여 있다)
- 각 posting 의 **company 에 그 공고를 낸 회사 이름을 반드시 적어라.**
- **건축설계 사무소의 신입·인턴 공고만** 골라라.
  시공사 현장직, 인테리어 시공, 영업, 감리, CAD 오퍼레이터, 경력 3년 이상은 제외한다.
- 경력직만 뽑는 공고는 넣지 마라.
- 최대 10건까지만. 조건에 맞는 게 없으면 빈 배열로 둔다.
- **source_url 은 그 공고 제목 뒤 `<...>` 안에 있는 개별 공고 주소를 써라.**
  검색 결과 페이지 주소를 쓰면 안 된다 — 클릭해도 그 공고로 가지 않는다.
  개별 주소를 못 찾으면 그 공고는 넣지 마라.
"""


# 무료 티어는 분당 요청 수가 빡빡하다. 전역으로 호출 간격을 벌려서 429 를 애초에 줄인다.
_last_call = 0.0
_call_lock = asyncio.Lock()

RETRYABLE = ("503", "UNAVAILABLE", "500", "INTERNAL")

# 무료 티어 한도는 **모델마다 따로** 걸린다 (quotaId: ...PerProjectPerModel).
# 그래서 한 모델이 하루치를 다 쓰면 다음 모델로 넘어가면 계속 돌 수 있다.
_exhausted: set[str] = set()


def _is_retryable(e: Exception) -> bool:
    return any(k in str(e) for k in RETRYABLE)


def _is_daily_quota(e: Exception) -> bool:
    """분당 한도(잠깐 기다리면 풀림)와 일일 한도(오늘은 끝)를 구분한다."""
    s = str(e)
    if "429" not in s and "RESOURCE_EXHAUSTED" not in s:
        return False
    return "PerDay" in s or "per day" in s.lower()


def _models(cfg: dict) -> list[str]:
    m = cfg.get("models") or [cfg["model"]]
    return [x for x in m if x not in _exhausted] or [m[0]]


def _client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(".env 에 GEMINI_API_KEY 가 없습니다")
    return genai.Client(api_key=key)


def extract_one(
    client: genai.Client, office: Office, url: str, page_text: str, cfg: dict[str, Any]
) -> tuple[str, Optional[OfficeReport], Optional[str]]:
    """한 오피스의 페이지 텍스트 → OfficeReport. 실패해도 예외를 밖으로 내보내지 않는다."""
    prompt = USER.format(
        office_id=office.id,
        name=" / ".join(office.name.values()) or office.id,
        country=office.country,
        city=office.city or "미상",
        url=url,
        today=date.today().isoformat(),
        page_text=budget_pages(page_text),
        board_note=BOARD_NOTE if (office.tier == "job_board") else "",
    )
    rcfg = cfg["research"]
    attempts = rcfg.get("max_retries", 3)
    resp = None
    used = None
    last_err = None
    for model_name in _models(cfg):
      used = model_name
      for attempt in range(attempts):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM.format(out_lang=OUT_LANG[cfg.get("locale", "ko")]),
                    response_mime_type="application/json",
                    response_schema=OfficeReport,
                    temperature=0,
                ),
            )
            break
        except Exception as e:
            if _is_daily_quota(e):
                # 이 모델은 오늘 끝. 재시도해도 소용없으니 다음 모델로.
                _exhausted.add(model_name)
                resp = None
                break
            if attempt < attempts - 1 and (_is_retryable(e) or "429" in str(e)):
                # 분당 한도/과부하는 기다리면 풀린다. 지수 백오프 + 지터.
                time.sleep(min(60, 2 ** attempt * rcfg.get("retry_base_seconds", 8))
                           + random.uniform(0, 2))
                continue
            # 재시도를 다 썼어도 한도/과부하 계열이면 다음 모델로 넘어간다.
            # 모델마다 할당량이 따로라서, 여기서 포기하면 남은 모델을 두고 버리는 셈이다.
            if _is_retryable(e) or "429" in str(e):
                last_err = f"{type(e).__name__}: {str(e)[:120]}"
                resp = None
                break
            return office.id, None, f"{type(e).__name__}: {str(e)[:160]}"
      if resp is not None:
        break
    if resp is None:
        return office.id, None, last_err or f"모든 모델 한도 소진 (마지막: {used})"

    report = resp.parsed
    if report is None:
        return office.id, None, f"구조화 출력 없음: {(resp.text or '')[:120]}"

    # 모델이 id 를 틀리게 채우는 경우가 있어 여기서 강제한다
    report.office_id = office.id
    report.careers_url_found = report.careers_url_found or url
    kept = [p for p in report.postings if p.source_url and p.source_url.startswith("http")]
    if len(kept) != len(report.postings):
        report.unresolved.append(f"출처 URL 없는 공고 {len(report.postings) - len(kept)}건 폐기")
        report.postings = kept
    for p in report.postings:
        p.office_id = office.id
    return office.id, report, None


async def extract_many(
    pages: list[tuple[Office, str, str]], cfg: dict[str, Any]
) -> list[tuple[str, Optional[OfficeReport], Optional[str]]]:
    """[(office, url, page_text), ...] 를 병렬 추출.
    SDK 가 동기라서 스레드로 돌린다 — 무료 티어 분당 제한을 넘지 않게 동시 수를 묶는다."""
    if not pages:
        return []
    client = _client()
    sem = asyncio.Semaphore(cfg["research"]["max_parallel"])

    gap = cfg["research"].get("min_seconds_between_calls", 6)

    async def guarded(item):
        office, url, text = item
        async with sem:
            # 호출 시각을 전역으로 벌린다 (분당 한도 회피)
            async with _call_lock:
                global _last_call
                wait = gap - (time.monotonic() - _last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                _last_call = time.monotonic()
            return await asyncio.to_thread(extract_one, client, office, url, text, cfg)

    return await asyncio.gather(*(guarded(p) for p in pages))
