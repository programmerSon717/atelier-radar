# 대기 중인 것 (세션 끊겨도 여기 보고 이어가기)

## 사용자가 줘야 진행되는 것
- [ ] **텔레그램 `/start`** — @atelierRader_bot 에서 /start 누른 뒤
      `./.venv/bin/python tools/get_chat_id.py` 실행 → .env 에 TELEGRAM_CHAT_IDS 추가
      (이거 없으면 발송이 안 되고 --dry-run 으로만 돈다)
- [ ] 여자친구분도 알림 받을지 (받으면 그분도 봇에 /start 필요)

## 다음에 할 것
1. **careers_url 계속 채우기** — 현재 17/43. 남은 곳은 아래 "URL 미해결" 참조
2. GitHub Actions 워크플로 (30분 watch + 주 1회 sweep)
3. zh_TW 전환 — locale 한 줄 + zh_TW.yaml 네이티브급으로 다듬기 (현재는 초벌 번역)

## 결정된 것
- **LLM: Gemini** (사용자 키). 무료 티어.
  검색 그라운딩은 429(할당량 없음) → 안 쓴다. 대신 httpx 로 페이지를 직접 긁어서 넘긴다.
  모델: gemini-3.5-flash. 프로 모델(gemini-3.1-pro-preview)은 무료 할당량 없음.
- 일본 타겟 B안: 전부 추적하되 언어요건 라벨만 붙인다
- 켄고쿠마는 인턴→정규직 공식 경로 없음 (`data/verified/kkaa.yaml`)

## 알려진 한계
- **JS 렌더링 페이지는 못 긁는다.** 특히 한국의 `*.recruiter.co.kr` ATS 는 전부 0자.
  → 잡코리아 회사페이지로 우회 (희림에서 검증됨). 사람인도 같은 방식 가능.
- tw-jjp(潘冀) 는 자사 채용 URL 미발견, 104 는 403 차단.

## URL 미해결 (26곳)
JP: mjd, takenaka, sanaa, nishizawa, toyoito, ando, oh, soufujimoto, kkaa-seoul 외
KR: samoo, haeahn, kunwon, dagroup, 101, massstudies, iarc, wondoshi, unsangdong,
    kkaa-seoul, gensler-seoul, aedas-seoul, sigongtech
TW: jjp, artech(SPA), daju, formosstudio, helei, cosine, zhujian, jingxiang
