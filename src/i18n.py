"""공고 내용을 한국어·영어·번체중문 세 벌로 만든다.

공고는 일본어·중국어·영어로 올라온다. 그대로 두면 읽을 수 없고, 기계적으로 옮기면
"応募" 가 "응모" 로 나온다. 그래서 **뜻이 통하게 옮긴다** — 다만 지어내지는 않는다.
없는 항목은 비운 채로 둔다. 항목 수를 줄이지도 않는다.

한 번의 호출로 세 언어를 다 만든다. 따로 부르면 용어가 갈린다.
"""
import hashlib
import json
from typing import Any, Optional

FIELDS_TEXT = ("title", "summary", "employment_type", "process", "apply_how",
               "language_required", "salary", "notes", "gate_label", "gate_reason",
               "gate_evidence", "gate_action", "pay_note")
FIELDS_LIST = ("responsibilities", "qualifications", "preferred", "firm_projects",
               "blockers_desc", "soft_desc", "met", "unknowns", "fit_why")

LANGS = ("ko", "en", "zh_TW")

# 되풀이되는 말은 미리 못 박는다. 공고마다 다르게 옮기면 목록이 읽히지 않는다.
GLOSSARY = """\
| 한국어 | English | 繁體中文 |
|---|---|---|
| 지원 가능 | Open to foreign applicants | 開放外籍應徵 |
| 문의 필요 | Needs confirmation | 需要詢問確認 |
| 국내 대학 졸업·유학생 전형 — 해당 없음 | Domestic-degree / international-student track — not eligible | 限當地大學畢業·留學生 — 不符資格 |
| 어학시험·현지어 요구 | Local-language test required | 需要當地語言檢定 |
| 지원 불가 | Not open to foreign applicants | 不開放外籍應徵 |
| 추천 | Recommended | 推薦 |
| 중립 | Neutral | 中立 |
| 비추천 | Not recommended | 不推薦 |
| 신입공채 | New-graduate hiring | 新鮮人招募 |
| 전환형 인턴 | Internship with conversion to full-time | 可轉正實習 |
| 상시채용 | Year-round hiring | 常年招募 |
| 마감 | Deadline | 截止 |
| 담당 업무 | Responsibilities | 工作內容 |
| 자격 요건 | Requirements | 應徵資格 |
| 우대 사항 | Preferred | 加分條件 |
| 경력 0년 | No full-time experience | 無正職經驗 |
| 회사 전체 평균 | Company-wide average | 公司整體平均 |
"""

SYSTEM = """\
너는 건축 채용공고를 세 언어로 옮긴다. 한국어(ko), 영어(en), 번체중문(zh_TW).

지켜야 할 것:
1. **원문에 없는 것을 만들지 마라.** 항목을 늘리지도 줄이지도 않는다.
   리스트는 **들어온 개수와 순서를 그대로** 지킨다.
2. 직역하지 마라. 그 나라 채용공고가 실제로 쓰는 말로 옮긴다.
   영어는 미국 건축사무소 채용공고 문체, 번체중문은 대만 사무소 공고 문체로 쓴다.
   "応募" 를 "응모" 라고 옮기는 식의 기계적 번역은 하지 마라 — "지원" 이다.
3. 고유명사(회사명·프로젝트명·역명·상 이름)는 **원문 표기 그대로** 둔다.
   한글 음을 지어서 붙이지 마라 — "大林組" 를 "오바마구미" 라고 쓴 적이 있다. 확실하지
   않으면 원문만 둔다.
4. 자격 요건의 **수치·기간·급수·연도는 절대 바꾸지 마라** (TOEIC 700, N2, 2027년 2월 등).
5. 아래 용어표는 그대로 따른다.

{glossary}
"""


def source_hash(bundle: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]


def _schema() -> dict:
    one = {
        "type": "object",
        "properties": {
            **{f: {"type": "string"} for f in FIELDS_TEXT},
            **{f: {"type": "array", "items": {"type": "string"}} for f in FIELDS_LIST},
        },
    }
    return {"type": "object", "properties": {lang: one for lang in LANGS}}


def bundle_of(d: dict[str, Any]) -> dict[str, Any]:
    """공고 dict 에서 화면에 나가는 것만 뽑는다. 빈 값은 넣지 않는다."""
    out: dict[str, Any] = {}
    for f in FIELDS_TEXT:
        v = d.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = v
    for f in FIELDS_LIST:
        v = d.get(f)
        if isinstance(v, list) and v:
            out[f] = [x for x in v if isinstance(x, str) and x.strip()]
    return out


def translate(client, bundle: dict[str, Any], cfg: dict) -> Optional[dict[str, Any]]:
    """{ko: {...}, en: {...}, zh_TW: {...}}. 실패하면 None."""
    if not bundle:
        return None
    from google.genai import types

    from .extract import _models

    last: Exception | None = None
    prompt = ("아래 JSON 을 세 언어로 옮겨라. 키 이름과 리스트 길이는 그대로 두고 값만 옮긴다.\n\n"
              + json.dumps(bundle, ensure_ascii=False, indent=1))
    for model_name in _models(cfg):
        try:
            r = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM.format(glossary=GLOSSARY),
                    response_mime_type="application/json",
                    response_schema=_schema(),
                    temperature=0.2,
                ),
            )
            data = json.loads(r.text) if r.text else None
            if not data:
                continue
            # 리스트 길이가 어긋나면 원문을 잃은 것이다 — 그건 쓰지 않는다
            for lang in LANGS:
                got = data.get(lang) or {}
                for f in FIELDS_LIST:
                    if f in bundle and len(got.get(f) or []) != len(bundle[f]):
                        got[f] = bundle[f]
            return {lang: data.get(lang) or {} for lang in LANGS}
        except Exception as e:
            last = e
            continue
    import sys
    print(f"    번역 실패: {type(last).__name__}: {str(last)[:120]}", file=sys.stderr)
    return None
