# 배타니 모닝 브리핑 🛡️

매일 아침 **KST 07:00**에 GitHub Actions가 자동으로 실행하는 개인 IT·보안 뉴스 브리핑 시스템.

- 📰 **뉴스 수집**: Google News(국내 종합/AI/반도체/보안) + 데일리시큐 + GeekNews + The Hacker News + TechCrunch + Hacker News API
- 📈 **시장 스냅샷**: 국내 종목(pykrx) · 코스피/코스닥(yfinance) · 해외 주식/환율(yfinance) · 코인(업비트 공개 API)
- 🔥 **GitHub Trending** 수집
- 🤖 **Gemini 분석**: 기사 선별 → 3줄 요약 → 핵심 용어 → 엔지니어링 인사이트 → 중요도 별점 → 시장 코멘터리
- 💬 **Discord 웹훅**으로 임베드 발송 + **Notion 데이터베이스** 자동 적재
- 🌐 **웹 대시보드**: GitHub Pages에서 날짜별 아카이브 열람

## 구조

```
config/settings.json      ← 유일하게 수정해야 하는 파일 (피드/관심종목/모델)
src/
  common.py               공통 유틸 (설정 로딩, KST, HTML 정제)
  collectors/news.py      RSS + Google News + HN API
  collectors/market.py    pykrx / yfinance / 업비트
  collectors/trending.py  GitHub Trending 스크래핑
  analysis/gemini.py      프롬프트 + structured output 분석
  delivery/discord.py     임베드 발송 (뉴스+시세+트렌딩)
  delivery/notion.py      스키마 자동 마이그레이션 + 페이지 적재
dashboard/                무빌드 웹 대시보드 (vanilla JS)
data/latest.json          오늘의 브리핑 (대시보드가 읽음)
data/history/*.json       일별 아카이브 (30일 보관)
```

## 설정 바꾸기

`config/settings.json` 하나만 수정하면 됩니다:

| 키 | 내용 |
|---|---|
| `news.feeds` | 뉴스 소스. `type`: `rss` / `gnews`(구글뉴스 검색어) / `hn_api` |
| `market.*` | 관심 국내종목 코드 / 해외 티커 / 업비트 마켓 |
| `trending.languages` | 비워두면 전체, `["python"]` 등 언어 필터 |
| `gemini.model` | 기본 `gemini-3.6-flash` |
| `delivery.*` | Discord/Notion 개별 ON/OFF |

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env   # 키 입력 후
python -m src.main            # 전체 파이프라인
python -m src.collectors.news # 수집기만 단독 테스트
```

## 노션 데이터베이스

속성은 첫 실행 때 **자동 생성**됩니다 (출처/중요도/태그/주간/읽음).
추천 뷰는 수동으로 만드세요 (노션 UI에서):

1. **오늘의 브리핑** — 필터: 날짜=오늘, 정렬: 중요도 내림차순
2. **미읽음** — 필터: 읽음=체크 해제
3. **카테고리 보드** — 그룹핑: 카테고리
4. **주간 리뷰** — 그룹핑: 주간

## 배포 파이프라인

1. Actions 크론(UTC 22:00 = KST 07:00) → `python -m src.main`
2. `data/` 변경분을 저장소에 자동 커밋 (아카이브 축적)
3. `dashboard/` + `data/`를 GitHub Pages에 배포

## 필요 Secrets

| 이름 | 설명 |
|---|---|
| `GEMINI_API_KEY` | Gemini API 키 |
| `DISCORD_WEBHOOK_URL` | Discord 웹훅 URL |
| `NOTION_TOKEN` | Notion 인테그레이션 토큰 |
| `DATABASE_ID` | Notion 데이터베이스 ID |

## 최초 1회 수동 설정

1. 저장소 **공개** 전환 (Settings → General → Danger Zone)
2. Settings → Pages → Source를 **GitHub Actions**로 지정
3. 이후 매일 `https://<user>.github.io/<repo>/` 에서 대시보드 확인
