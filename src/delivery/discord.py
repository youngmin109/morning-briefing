"""Discord 웹훅 전송 — 뉴스 임베드 + 시세 카드 + GitHub Trending."""
import os

import requests

from src.common import load_settings

CATEGORY_COLORS = {
    "보안": 0xE74C3C, "클라우드": 0x3498DB, "AI": 0x9B59B6,
    "네트워크": 0x2ECC71, "인프라": 0xE67E22, "시장": 0xF1C40F,
}


def _fmt_change(pct: float) -> str:
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "─")
    return f"{arrow} {pct:+.2f}%"


def _market_embed(briefing: dict, market: dict) -> dict | None:
    kr = market.get("kr", {})
    us = market.get("us", {})
    groups = [
        ("🇰🇷 국내 지수/종목",
         [f"**{i['label']}** {i['price']:,} ({_fmt_change(i['change_pct'])})"
          for i in (kr.get("indices") or []) + (kr.get("stocks") or [])]),
        ("🌍 해외 주식/환율",
         [f"**{i['label']}** {i['price']:,} ({_fmt_change(i['change_pct'])})"
          for i in (us.get("stocks") or []) + (us.get("fx") or [])]),
        ("🪙 코인 (업비트 기준)",
         [f"**{i['label']}** {i['price']:,}원 ({_fmt_change(i['change_pct'])})"
          for i in market.get("crypto") or []]),
    ]
    fields = []
    for name, lines in groups:
        if lines:
            fields.append({"name": name, "value": "\n".join(lines)[:1024], "inline": False})
    if not fields:
        return None
    mb = briefing.get("market_briefing") or {}
    return {
        "title": f"📈 시장 브리핑 — {mb.get('headline', '오늘의 시장')}",
        "description": mb.get("commentary", ""),
        "color": 0x2ECC71,
        "fields": fields,
    }


def _trending_embed(trending: list[dict]) -> dict | None:
    if not trending:
        return None
    lines = [
        f"**{r['repo']}** ★{r['total_stars']:,} (+{r['period_stars']:,})\n"
        f"{('<' + r['url'] + '>') if r['url'] else ''}"
        for r in trending[:5]
    ]
    return {
        "title": "🔥 GitHub Trending TOP 5",
        "url": "https://github.com/trending",
        "description": "\n".join(lines)[:4000],
        "color": 0x95A5A6,
    }


def _article_embed(article: dict) -> dict:
    summary = "\n".join(f"• {s}" for s in article.get("summary", []))
    keywords = "\n".join(f"• {kw}" for kw in article.get("study_keywords", []))
    stars = "⭐" * int(article.get("importance", 3))
    fields = [
        {"name": f"📌 중요도 {'⭐' * int(article.get('importance', 3))}",
         "value": summary[:1024] or "요약 없음", "inline": False},
    ]
    if keywords:
        fields.append({"name": "💡 핵심 개념", "value": keywords[:1024], "inline": False})
    if article.get("tech_insight"):
        fields.append({"name": "🛡️ 엔지니어링 인사이트", "value": str(article["tech_insight"])[:1024], "inline": False})
    tags = ", ".join(f"`{t}`" for t in (article.get("tags") or [])[:3])
    if tags:
        fields.append({"name": "🏷️ 태그", "value": tags, "inline": False})
    return {
        "title": f"[{article.get('category', '보안')}] {article.get('title', '제목 없음')}",
        "url": article.get("link", ""),
        "color": CATEGORY_COLORS.get(article.get("category"), 0x3498DB),
        "footer": {"text": f"{article.get('source', '')} · {stars}"},
        "fields": fields,
    }


def send_briefing(date_str: str, briefing: dict, market: dict, trending: list[dict], settings=None) -> bool:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    dcfg = (settings or load_settings())["delivery"]
    if not dcfg.get("discord_enabled", True):
        print("[i] 설정에서 Discord 전송 비활성화됨")
        return False
    if not webhook:
        print("[!] DISCORD_WEBHOOK_URL 미설정 — 전송 생략")
        return False

    mb = briefing.get("market_briefing") or {}
    header = f"🌅 **오늘의 IT 모닝 브리핑 ({date_str})**"
    if mb.get("headline"):
        header += f"\n> {mb['headline']}"

    embeds = []
    market_e = _market_embed(briefing, market)
    if market_e:
        embeds.append(market_e)
    embeds.extend(_article_embed(a) for a in briefing.get("articles", []))
    trending_e = _trending_embed(trending)
    if trending_e:
        embeds.append(trending_e)

    batch_size = dcfg.get("discord_max_embeds_per_batch", 5)
    ok = True
    for i in range(0, len(embeds), batch_size):
        payload = {"content": header if i == 0 else "", "embeds": embeds[i:i + batch_size]}
        try:
            resp = requests.post(webhook, json=payload, timeout=15)
            if resp.status_code != 204:
                ok = False
                print(f"[!] Discord 전송 실패: {resp.status_code}, {resp.text[:200]}")
            else:
                print(f"  [OK] Discord 배치 전송 ({len(payload['embeds'])}개 임베드)")
        except Exception as e:
            ok = False
            print(f"[!] Discord 전송 예외: {e}")
    return ok
