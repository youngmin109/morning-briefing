"""Gemini 분석 모듈 — 뉴스 선별·요약·인사이트 + 시장 브리핑 생성.

기존 main.py의 재시도/마크다운펜스 방어 로직을 계승하고,
시장 코멘터리와 중요도 평가를 추가했다.
"""
import json
import os
import time

from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError

from src.common import load_settings

VALID_CATEGORIES = ["보안", "클라우드", "네트워크", "AI", "인프라", "시장"]


def _market_lines(market: dict) -> str:
    lines = []
    for group, label in [(market.get("kr", {}).get("indices"), "지수"),
                         (market.get("kr", {}).get("stocks"), "국내종목"),
                         (market.get("us", {}).get("stocks"), "해외종목"),
                         (market.get("us", {}).get("fx"), "환율"),
                         (market.get("crypto"), "코인")]:
        if not group:
            continue
        parts = [f"{i['label']} {i['price']:,} ({i['change_pct']:+.2f}%)" for i in group]
        lines.append(f"- {label}: " + ", ".join(parts))
    return "\n".join(lines) or "- 시세 데이터 없음"


def build_prompt(news_items: list[dict], market: dict, top_n: int) -> str:
    slim_news = [
        {"title": n["title"], "link": n["link"], "source": n["source"], "summary": n["summary"]}
        for n in news_items
    ]
    return f"""당신은 최상위 보안 아키텍처이자 IT 기술 교육자이며, 동시에 시장 분석가입니다.
오늘 수집된 자료를 분석하여 아래 두 파트를 반드시 지정된 JSON 구조로만 반환하세요.

## PART 1 — market_briefing
아래 시세 스냅샷을 바탕으로:
- headline: 오늘 시장 상태를 한 문장으로 요약 (예: "코스피 상승 마감, AI주 강세 주도")
- commentary: 전일 대비 변동의 추정 원인과 오늘 확인할 포인트를 2~3문장으로.
  (뉴스 기사 내용과 시세를 연결 지을 수 있으면 연결할 것. 근거가 부족하면 단정하지 말 것.)

## PART 2 — articles
수집된 기사 중 엔지니어 관점에서 기술적 가치가 높고 학습에 도움 되는 {top_n}개를 엄선하세요.
- 서로 다른 카테고리가 고루 담기도록 선별하세요.
- importance는 1(가벼운 소식)~5(반드시 알아야 함)로 평가하세요.
- category는 보안/클라우드/네트워크/AI/인프라/시장 중 택1.
- tags는 세부 키워드 최대 3개 (예: "0-day", "Kubernetes", "금리").

각 기사 항목:
1. title: 한국어 번역/정제된 제목
2. link: 원문 링크 (입력 그대로)
3. source: 출처 (입력 그대로)
4. category / importance / tags
5. summary: 3줄 핵심 사실 요약 (문장 배열)
6. study_keywords: 핵심 용어 2~3개와 짧은 설명 ("용어: 설명" 형식 문자열 배열)
7. tech_insight: 실무 엔지니어 관점의 시사점 또는 대응 방안 (1~2문장)

## 입력 데이터

### 뉴스 기사
{json.dumps(slim_news, ensure_ascii=False)}

### 시세 스냅샷
{_market_lines(market)}

## 반환 JSON 스키마
{{
  "market_briefing": {{
    "headline": "...",
    "commentary": "..."
  }},
  "articles": [
    {{
      "title": "...",
      "link": "...",
      "source": "...",
      "category": "보안",
      "importance": 5,
      "tags": ["태그1", "태그2"],
      "summary": ["문장1", "문장2", "문장3"],
      "study_keywords": ["용어1: 설명", "용어2: 설명"],
      "tech_insight": "..."
    }}
  ]
}}"""


def _strip_code_fence(raw_text: str) -> str:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()
    return raw_text


def analyze(news_items: list[dict], market: dict, settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    cfg = settings["gemini"]
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] GEMINI_API_KEY 미설정 — 분석 생략")
        return {"market_briefing": {}, "articles": []}

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(news_items, market, settings["news"]["top_n"])

    last_error = None
    for attempt in range(1, cfg.get("max_retries", 3) + 1):
        try:
            response = client.models.generate_content(
                model=cfg.get("model", "gemini-3.6-flash"),
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=cfg.get("timeout_seconds", 90) * 1000),
                ),
            )
            result = json.loads(_strip_code_fence(response.text))
            # 방어적 정규화
            articles = []
            for a in result.get("articles", []):
                a["importance"] = max(1, min(5, int(a.get("importance", 3))))
                if a.get("category") not in VALID_CATEGORIES:
                    a["category"] = "인프라"
                if isinstance(a.get("summary"), str):
                    a["summary"] = [a["summary"]]
                if isinstance(a.get("tags"), str):
                    a["tags"] = [a["tags"]]
                articles.append(a)
            return {
                "market_briefing": result.get("market_briefing") or {},
                "articles": articles,
            }
        except (ServerError, APIError) as e:
            last_error = e
            print(f"[!] Gemini API 일시적 오류 (시도 {attempt}/{cfg.get('max_retries', 3)}): {e}")
            time.sleep(attempt * 3)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            print(f"[!] 응답 파싱 오류 (시도 {attempt}/{cfg.get('max_retries', 3)}): {e}")
            time.sleep(2)
    raise RuntimeError(f"Gemini 분석 실패: {last_error}")


if __name__ == "__main__":
    print("[테스트] 분석 모듈은 전체 파이프라인에서 실행하세요: python -m src.main")
