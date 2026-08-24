"""전체 파이프라인 오케스트레이터.

수집 → 중복제거 → Gemini 분석 → 데이터 파일 저장 → Discord 전송 → Notion 적재
각 단계는 격리되어 있어, 일부가 실패해도 나머지는 동작한다.
"""
import json
import os
import sys
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.common import load_settings, norm_link, today_str, PROJECT_ROOT, KST
from src.collectors.news import collect_news
from src.collectors.market import collect_market
from src.collectors.trending import collect_trending
from src.analysis.gemini import analyze
from src.delivery.discord import send_briefing
from src.delivery.notion import push_articles


def load_seen_urls(lookback_days: int) -> set[str]:
    """최근 N일치 history에서 이미 발송된 기사 URL 수집."""
    seen: set[str] = set()
    history_dir = PROJECT_ROOT / "data" / "history"
    if not history_dir.exists():
        return seen
    cutoff = (datetime.now(KST) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    for path in history_dir.glob("*.json"):
        if path.stem < cutoff:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for a in data.get("articles", []):
                link = a.get("link")
                if link:
                    seen.add(norm_link(link))
        except Exception as e:
            print(f"[!] history 읽기 실패 ({path.name}): {e}")
    return seen


def save_data(date_str: str, briefing: dict, market: dict, trending: list[dict]) -> None:
    payload = {
        "date": date_str,
        "generated_at": datetime.now(KST).isoformat(),
        "market_briefing": briefing.get("market_briefing", {}),
        "articles": briefing.get("articles", []),
        "market": market,
        "trending": trending,
    }
    latest_path = PROJECT_ROOT / "data" / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    cfg = load_settings()["data"]
    history_dir = PROJECT_ROOT / cfg["history_dir"]
    history_dir.mkdir(parents=True, exist_ok=True)
    with open(history_dir / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 오래된 히스토리 정리 + 아카이브 인덱스 갱신
    retention = cfg["history_retention_days"]
    cutoff = (datetime.now(KST) - timedelta(days=retention)).strftime("%Y-%m-%d")
    for path in history_dir.glob("*.json"):
        if path.stem[:10] < cutoff:
            path.unlink()
            print(f"  [정리] 오래된 히스토리 삭제: {path.name}")
    dates = sorted((p.stem for p in history_dir.glob("*.json")), reverse=True)
    with open(PROJECT_ROOT / "data" / "index.json", "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False)
    print(f"  [OK] 데이터 저장: {latest_path.relative_to(PROJECT_ROOT)} + history({len(dates)}일)")


def main() -> int:
    settings = load_settings()
    date_str = today_str()
    print(f"=== boan-news 파이프라인 시작 ({date_str}) ===")

    print("[1/6] 뉴스 수집...")
    news = collect_news(settings)

    print("[2/6] 시세 수집...")
    try:
        market = collect_market(settings)
    except Exception as e:
        print(f"[!] 시세 수집 실패(무시하고 계속): {e}")
        market = {"kr": {}, "us": {}, "crypto": []}

    print("[3/6] GitHub Trending 수집...")
    trending = collect_trending(settings)

    print("[4/6] Gemini 분석...")
    lookback = settings["news"].get("dedup_lookback_days", 7)
    seen = load_seen_urls(lookback)
    fresh = [n for n in news if norm_link(n["link"]) not in seen]
    print(f"  전체 {len(news)}건 중 신규 {len(fresh)}건 (최근 {lookback}일 중복 제외)")
    target = fresh or news  # 전부 중복이면 그래도 상위 몇 건은 보내도록 폴백
    if not target:
        print("[!] 수집된 기사 없음 — 종료")
        return 1
    briefing = analyze(target, market, settings)
    articles_count = len(briefing.get("articles", []))
    print(f"  엄선된 기사 {articles_count}건")

    print("[5/6] 데이터 저장...")
    save_data(date_str, briefing, market, trending)

    print("[6/6] 전달 (Discord → Notion)...")
    send_ok = send_briefing(date_str, briefing, market, trending, settings)
    notion_count = push_articles(date_str, briefing.get("articles", []), settings)

    print(f"=== 완료: 기사 {articles_count}건 | Discord {'성공' if send_ok else '실패/생략'} | Notion {notion_count}건 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
