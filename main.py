import os
import json
from datetime import datetime
import feedparser
from notion_client import Client
from google import genai
from google.genai import types

# GitHub Secrets에서 환경변수로 주입받을 키 설정
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_FEEDS = [
    "http://feeds.feedburner.com/geeknews-feed",
    "https://techcrunch.com/feed/"
]

def fetch_recent_news():
    raw_news = []
    for feed_url in RSS_FEEDS:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:5]:
            raw_news.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", "")[:300]
            })
    return raw_news

def analyze_and_summarize(news_items):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    당신은 IT 전문 에디터입니다. 아래 수집된 기사 중 오늘 가장 중요한 IT/기술/보안 기사 5개를 엄선하세요.
    각 기사마다 3줄 요약과 핵심 카테고리(예: AI, 보안, 클라우드, 개발, 비즈니스 등)를 분류하세요.
    반드시 한국어로 작성하고 지정된 JSON 형식으로만 반환하세요.

    기사 데이터:
    {json.dumps(news_items, ensure_ascii=False)}

    반환 스키마:
    [
      {{
        "title": "뉴스 제목",
        "link": "원문 링크",
        "category": "AI",
        "summary": "1. 요약 첫번째 줄\\n2. 요약 두번째 줄\\n3. 요약 세번째 줄"
      }}
    ]
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

def push_to_notion(selected_news):
    notion = Client(auth=NOTION_TOKEN)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for item in selected_news:
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "제목": {
                    "title": [{"text": {"content": item["title"]}}]
                },
                "URL": {
                    "url": item["link"]
                },
                "카테고리": {
                    "select": {"name": item["category"]}
                },
                "날짜": {
                    "date": {"start": today_str}
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"text": {"content": item["summary"]}}
                        ]
                    }
                }
            ]
        )

if __name__ == "__main__":
    news_data = fetch_recent_news()
    processed_news = analyze_and_summarize(news_data)
    push_to_notion(processed_news)
    print("완료: 노션 데이터베이스에 기사 적재 성공.")