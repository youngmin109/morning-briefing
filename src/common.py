"""프로젝트 공통 유틸리티 — 설정 로딩, KST 시간, HTML 정제."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))

_SETTINGS_CACHE: dict | None = None


def load_settings() -> dict:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is None:
        path = PROJECT_ROOT / "config" / "settings.json"
        with open(path, encoding="utf-8") as f:
            _SETTINGS_CACHE = json.load(f)
    return _SETTINGS_CACHE


def kst_now() -> datetime:
    return datetime.now(KST)


def today_str(fmt: str = "%Y-%m-%d") -> str:
    return kst_now().strftime(fmt)


def iso_week_label(dt: datetime | None = None) -> str:
    """예: 2026-W35 — 노션 '주간' 속성용."""
    dt = dt or kst_now()
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


_TAG_RE = re.compile(r"<[^>]+>")


def norm_link(url: str) -> str:
    """URL 비교용 정규화 — 해시/트레일링 슬래시 제거. 쿼리는 유지(id 기반 피드 대응)."""
    return (url or "").split("#")[0].rstrip("/")


def strip_html(text: str) -> str:
    """RSS summary의 HTML 태그/엔티티 제거."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()
