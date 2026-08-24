"""뉴스 수집기 — RSS + Google News RSS + Hacker News API.

국내 중심(Google News 한국어 쿼리) + 해외 보조 소스를 config/settings.json에서 관리한다.
소스 하나가 죽어도 전체 파이프라인이 죽지 않도록 에러 격리 필수.
"""
import requests
import feedparser

from urllib.parse import quote

from src.common import load_settings, norm_link, strip_html


def _fetch_rss(feed: dict, limit: int) -> list[dict]:
    parsed = feedparser.parse(feed["url"])
    items = []
    for entry in parsed.entries[:limit]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        summary = strip_html(entry.get("summary") or entry.get("description", ""))[:400]
        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source": feed["name"],
            "region": feed.get("region", "kr"),
        })
    return items


def _fetch_gnews(feed: dict, limit: int) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={quote(feed['query'])}&hl=ko&gl=KR&ceid=KR:ko"
    parsed = feedparser.parse(url)
    items = []
    for entry in parsed.entries[:limit]:
        title = entry.get("title", "").strip()
        if not title:
            continue
        # Google News 제목은 "기사제목 - 언론사" 형태 → 출처 분리
        source_name = feed["name"]
        src = entry.get("source")
        if isinstance(src, dict) and src.get("title"):
            source_name = src["title"]
            suffix = f" - {src['title']}"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
        link = (entry.get("link") or "").strip()
        summary = strip_html(entry.get("summary") or "")[:400]
        items.append({
            "title": title,
            "link": link,
            "summary": summary or f"Google News 검색 결과 ({source_name})",
            "source": source_name,
            "region": feed.get("region", "kr"),
        })
    return items


def _fetch_hackernews(feed: dict, limit: int) -> list[dict]:
    resp = requests.get(feed["url"], timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for hit in data.get("hits", [])[:limit]:
        title = (hit.get("title") or "").strip()
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        points = hit.get("points", 0)
        if not title:
            continue
        items.append({
            "title": title,
            "link": link,
            "summary": f"Hacker News 프론트페이지 ({points} points)",
            "source": feed["name"],
            "region": feed.get("region", "global"),
        })
    return items


_FETCHERS = {"rss": _fetch_rss, "hn_api": _fetch_hackernews, "gnews": _fetch_gnews}


def collect_news(settings: dict | None = None) -> list[dict]:
    cfg = (settings or load_settings())["news"]
    all_items: list[dict] = []
    for feed in cfg["feeds"]:
        fetcher = _FETCHERS.get(feed.get("type"))
        try:
            got = fetcher(feed, feed.get("per_feed_limit", cfg.get("per_feed_limit", 8)))
            print(f"  [OK] {feed['name']}: {len(got)}건")
            all_items.extend(got)
        except Exception as e:
            print(f"  [SKIP] {feed['name']} 수집 실패(무시됨): {e}")
    # URL 중복 제거 (같은 기사 여러 피드 도착 방지)
    seen, unique = set(), []
    for item in all_items:
        key = norm_link(item["link"])
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    max_articles = cfg.get("max_articles_for_llm", 45)
    return unique[:max_articles]


if __name__ == "__main__":
    print("[테스트] 뉴스 수집기 단독 실행")
    result = collect_news()
    by_source = {}
    for r in result:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    print(f"총 {len(result)}건: {by_source}")
