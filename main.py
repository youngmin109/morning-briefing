import os
import json
import time
from datetime import datetime
import requests
import feedparser
from notion_client import Client
from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError

# .env 파일이 있으면 로드 (로컬 개발 편의용)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 1. 환경변수 설정 (GitHub Secrets 주입)
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 2. 전문 보안 & 클라우드/IT RSS 목록
RSS_FEEDS = [
    "https://www.boannews.com/media/news_rss.xml",     # 보안뉴스
    "https://www.dailysecu.com/rss/allArticle.xml",    # 데일리시큐
    "https://feeds.feedburner.com/TheHackersNews",     # The Hacker News
    "http://feeds.feedburner.com/geeknews-feed",       # GeekNews
    "https://techcrunch.com/feed/"                     # TechCrunch
]

def fetch_recent_news():
    raw_news = []
    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:5]:
                raw_news.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[:400]
                })
        except Exception as e:
            print(f"[!] RSS 파싱 에러 ({feed_url}): {e}")
    return raw_news

def analyze_and_summarize(news_items, max_retries=3):
    if not GEMINI_API_KEY:
        print("[!] GEMINI_API_KEY가 설정되지 않았습니다.")
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    당신은 최상위 보안 아키텍트이자 IT 기술 교육자입니다.
    수집된 기사 중 엔지니어 관점에서 기술적 가치가 높고 학습에 도움 되는 최신 뉴스 5개를 엄선하세요.
    
    각 기사마다 다음 항목을 도출하여 반드시 지정된 JSON 구조로만 반환하세요:
    1. title: 기사 제목 (한국어 번역/정제)
    2. link: 원문 링크
    3. category: 보안 / 클라우드 / 네트워크 / AI / 인프라 중 택1
    4. summary: 3줄 핵심 사실 요약 (문장 리스트)
    5. study_keywords: 관련 핵심 기술 용어 2~3개와 간단한 설명
    6. tech_insight: 실무 엔지니어 관점에서의 시사점 또는 보안 대응 방안 (1~2문장)

    기사 데이터:
    {json.dumps(news_items, ensure_ascii=False)}

    반환 JSON 스키마:
    [
      {{
        "title": "기사 제목",
        "link": "원문 링크",
        "category": "보안",
        "summary": [
          "첫번째 요약 문장",
          "두번째 요약 문장",
          "세번째 요약 문장"
        ],
        "study_keywords": [
          "용어1: 용어에 대한 핵심 개념 설명",
          "용어2: 용어에 대한 핵심 개념 설명"
        ],
        "tech_insight": "엔지니어 관점 대응책 및 인사이트 내용"
      }}
    ]
    """
    
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text.strip()
            
            # 마크다운 코드블록 서식 제거 방어 코드
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()
                
            return json.loads(raw_text)
            
        except (ServerError, APIError) as e:
            print(f"[!] Gemini API 일시적 오류 발생 (시도 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(attempt * 3)
            else:
                raise
        except json.JSONDecodeError as e:
            print(f"[!] JSON 파싱 오류 (시도 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(2)
            else:
                raise
    return []

def push_to_notion(selected_news):
    if not NOTION_TOKEN or not DATABASE_ID:
        print("[!] Notion 토큰 또는 Database ID가 설정되지 않아 Notion 적재를 건너뜁니다.")
        return
        
    notion = Client(auth=NOTION_TOKEN)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for item in selected_news:
        try:
            summary_list = item.get("summary", [])
            if isinstance(summary_list, str):
                summary_list = [summary_list]

            keywords_list = item.get("study_keywords", [])
            if isinstance(keywords_list, str):
                keywords_list = [keywords_list]

            children_blocks = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "📌 핵심 요약"}}]
                    }
                }
            ]
            
            for line in summary_list:
                children_blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })
            
            children_blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "💡 핵심 개념 & 용어 학습"}}]
                }
            })
            for kw in keywords_list:
                children_blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": kw}}]
                    }
                })

            children_blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"엔지니어링 인사이트: {item.get('tech_insight', '')}"}}],
                    "icon": {"emoji": "🛡️"}
                }
            })

            notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties={
                    "제목": {
                        "title": [{"text": {"content": item.get("title", "제목 없음")}}]
                    },
                    "URL": {
                        "url": item.get("link", "")
                    },
                    "카테고리": {
                        "select": {"name": item.get("category", "보안")}
                    },
                    "날짜": {
                        "date": {"start": today_str}
                    }
                },
                children=children_blocks
            )
        except Exception as e:
            print(f"[!] Notion 페이지 생성 실패 ({item.get('title')}): {e}")

def send_to_discord(selected_news):
    if not DISCORD_WEBHOOK_URL:
        print("[!] DISCORD_WEBHOOK_URL이 설정되지 않아 디스코드 전송을 건너뜁니다.")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    embeds = []
    
    category_colors = {
        "보안": 0xE74C3C,      # Red
        "클라우드": 0x3498DB,  # Blue
        "AI": 0x9B59B6,        # Purple
        "네트워크": 0x2ECC71,  # Green
        "인프라": 0xE67E22     # Orange
    }

    for item in selected_news:
        summary_list = item.get("summary", [])
        if isinstance(summary_list, str):
            summary_list = [summary_list]
        summary_lines = "\n".join([f"• {s}" for s in summary_list])

        keywords_list = item.get("study_keywords", [])
        if isinstance(keywords_list, str):
            keywords_list = [keywords_list]
        keywords_lines = "\n".join([f"• {kw}" for kw in keywords_list])
        
        fields = [
            {"name": "📌 3줄 요약", "value": summary_lines[:1024] if summary_lines else "요약 없음", "inline": False}
        ]
        
        if keywords_lines:
            fields.append({"name": "💡 핵심 키워드", "value": keywords_lines[:1024], "inline": False})
            
        if item.get("tech_insight"):
            fields.append({"name": "🛡️ 보안 인사이트", "value": item["tech_insight"][:1024], "inline": False})

        embed = {
            "title": f"[{item.get('category', '보안')}] {item.get('title', '제목 없음')}",
            "url": item.get("link", ""),
            "color": category_colors.get(item.get("category"), 0x3498DB),
            "fields": fields
        }
        embeds.append(embed)

    # 디스코드는 1회 요청당 최대 10개의 임베드 지원
    for i in range(0, len(embeds), 5):
        chunk = embeds[i:i+5]
        payload = {
            "content": f"🚨 **오늘의 핵심 IT/보안 모닝 브리핑 ({today_str})**" if i == 0 else "",
            "embeds": chunk
        }
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
            if resp.status_code == 204:
                print("[+] Discord 웹후크 전송 성공")
            else:
                print(f"[!] Discord 전송 실패: {resp.status_code}, {resp.text}")
        except Exception as e:
            print(f"[!] Discord 전송 중 예외 발생: {e}")

if __name__ == "__main__":
    print("[1/4] 전문 RSS 수집 중...")
    news_data = fetch_recent_news()
    print(f" -> 수집된 기사 수: {len(news_data)}개")
    
    print("[2/4] LLM 분석 및 리포트 생성 중...")
    processed_news = analyze_and_summarize(news_data)
    print(f" -> 엄선된 기사 수: {len(processed_news)}개")
    
    print("[3/4] Notion에 리포트 적재 중...")
    push_to_notion(processed_news)
    
    print("[4/4] Discord 알림 발송 중...")
    send_to_discord(processed_news)
    
    print("완료: 모든 작업이 성공적으로 종료되었습니다.")