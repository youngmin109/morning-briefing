"""Notion 적재 — 스키마 자동 마이그레이션 + 페이지 생성.

Notion API 2025-09-03(데이터소스 기반)과 구버전(DB 객체에 properties)을 모두 지원한다.
기존 DB(제목/날짜/카테고리/URL)를 유지하면서 출처·중요도·태그·주간·읽음 속성을
첫 실행 때 자동 추가한다 (멱등, 삭제 없음).
"""
import os

import requests as http_client
from notion_client import Client

from src.common import iso_week_label

NEW_PROPERTIES = {
    "출처": {"select": {}},
    "중요도": {"number": {"format": "number"}},
    "태그": {"multi_select": {"options": []}},
    "주간": {"select": {}},
    "읽음": {"checkbox": {}},
}

CATEGORY_OPTIONS = ["보안", "클라우드", "네트워크", "AI", "인프라", "시장"]

_NOTION_API = "https://api.notion.com/v1"
# 데이터소스 엔드포인트가 존재하는 최소 버전. 구버전 서버 응답과의 호환도 이 헤더로 커버된다.
_NOTION_VERSION = "2025-09-03"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _data_source_id(notion: Client, database_id: str) -> str | None:
    """신버전 API면 DB에 묶인 data_source id를 반환, 못 찾으면 None."""
    db = notion.databases.retrieve(database_id=database_id)
    ds_list = db.get("data_sources") or []
    return ds_list[0]["id"] if ds_list else None


def _ds_get_properties(token: str, ds_id: str) -> dict:
    r = http_client.get(f"{_NOTION_API}/data_sources/{ds_id}", headers=_headers(token), timeout=20)
    r.raise_for_status()
    return r.json().get("properties", {})


def _ds_patch_properties(token: str, ds_id: str, props: dict) -> dict:
    r = http_client.patch(
        f"{_NOTION_API}/data_sources/{ds_id}",
        headers=_headers(token),
        json={"properties": props},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("properties", {})


def _merge_updates(existing: dict) -> dict:
    """없는 속성 추가 + 기존 select 옵션 보존하면서 누락 옵션만 병합."""
    updates: dict = {}
    for name, schema in NEW_PROPERTIES.items():
        if name not in existing:
            updates[name] = schema

    cat = existing.get("카테고리")
    if isinstance(cat, dict) and cat.get("type") == "select":
        have = {o["name"] for o in cat["select"].get("options", [])}
        merged = [{"name": n} for n in CATEGORY_OPTIONS if n not in have]
        if merged:
            # select 옵션 갱신은 전체 교체이므로 기존 옵션을 함께 보내야 한다
            updates["카테고리"] = {
                "select": {"options": cat["select"].get("options", []) + merged}
            }
    return updates


def ensure_schema(token: str, database_id: str) -> dict:
    """없는 속성만 추가한다 (멱등). 최종 속성 맵 반환."""
    notion = Client(auth=token)
    ds_id = _data_source_id(notion, database_id)

    if ds_id:  # 신버전(2025-09-03+): 데이터소스 엔드포인트 사용
        existing = _ds_get_properties(token, ds_id)
        updates = _merge_updates(existing)
        if not updates:
            print("  [OK] Notion 스키마 이미 최신")
            return existing
        result = _ds_patch_properties(token, ds_id, updates)
        print(f"  [OK] Notion 속성 자동 추가: {', '.join(k for k in updates if k != '카테고리')}")
        return result

    # 구버전 폴백: DB 객체에 properties가 직접 있는 경우
    db = notion.databases.retrieve(database_id=database_id)
    existing = db.get("properties", {})
    updates = _merge_updates(existing)
    if not updates:
        print("  [OK] Notion 스키마 이미 최신 (legacy)")
        return existing
    result = notion.databases.update(database_id=database_id, properties=updates)
    print(f"  [OK] Notion 속성 자동 추가(legacy): {', '.join(updates)}")
    return result.get("properties", existing)


def _children_blocks(article: dict) -> list[dict]:
    blocks = [
        {"object": "block", "type": "heading_2",
         "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📌 핵심 요약"}}]}},
    ]
    for line in article.get("summary", []):
        blocks.append({"object": "block", "type": "bulleted_list_item",
                       "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": str(line)}}]}})
    blocks.append(
        {"object": "block", "type": "heading_2",
         "heading_2": {"rich_text": [{"type": "text", "text": {"content": "💡 핵심 개념 & 용어 학습"}}]}})
    for kw in article.get("study_keywords", []):
        blocks.append({"object": "block", "type": "bulleted_list_item",
                       "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": str(kw)}}]}})
    if article.get("tech_insight"):
        blocks.append(
            {"object": "block", "type": "callout",
             "callout": {
                 "rich_text": [{"type": "text",
                                "text": {"content": f"엔지니어링 인사이트: {article['tech_insight']}"}}],
                 "icon": {"emoji": "🛡️"},
             }})
    link = article.get("link", "")
    if link:
        blocks.append(
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{
                 "type": "text",
                 "text": {"content": "🔗 원문 읽기 → ", "link": None},
             }, {
                 "type": "text",
                 "text": {"content": link, "link": {"url": link}},
             }]}})
    return blocks


def push_articles(date_str: str, articles: list[dict], settings=None) -> int:
    from src.common import load_settings

    cfg = (settings or load_settings())["delivery"]
    token, database_id = os.environ.get("NOTION_TOKEN"), os.environ.get("DATABASE_ID")
    if not cfg.get("notion_enabled", True):
        print("[i] 설정에서 Notion 전송 비활성화됨")
        return 0
    if not token or not database_id:
        print("[!] NOTION_TOKEN/DATABASE_ID 미설정 — Notion 적재 생략")
        return 0

    try:
        ensure_schema(token, database_id)
    except Exception as e:
        print(f"[!] Notion 스키마 확인 실패(적재는 계속): {e}")

    week = iso_week_label()
    notion = Client(auth=token)
    created = 0
    for article in articles:
        try:
            tags = [str(t)[:96] for t in (article.get("tags") or [])[:3]]
            notion.pages.create(
                parent={"database_id": database_id},
                properties={
                    "제목": {"title": [{"text": {"content": article.get("title", "제목 없음")}}]},
                    "URL": {"url": article.get("link", "")},
                    "카테고리": {"select": {"name": article.get("category", "보안")}},
                    "출처": {"select": {"name": article.get("source", "기타")[:96]}},
                    "중요도": {"number": int(article.get("importance", 3))},
                    "태그": {"multi_select": [{"name": t} for t in tags]},
                    "주간": {"select": {"name": week}},
                    "날짜": {"date": {"start": date_str}},
                    "읽음": {"checkbox": False},
                },
                children=_children_blocks(article),
            )
            created += 1
            print(f"  [OK] Notion: {article.get('title', '')[:40]}")
        except Exception as e:
            print(f"[!] Notion 페이지 생성 실패 ({article.get('title', '')[:30]}): {e}")
    return created
