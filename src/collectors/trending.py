"""GitHub Trending 수집기.

공식 API가 없어서 github.com/trending 페이지를 파싱한다.
HTML 구조가 바뀌면 [SKIP] 로그로 조용히 건너뛴다.
"""
import requests
from bs4 import BeautifulSoup

from src.common import load_settings


def _parse_trending(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    repos = []
    for article in soup.select("article.Box-row"):
        link = article.select_one("h2 a")
        if not link:
            continue
        repo_path = (link.get("href") or "").strip("/")
        if not repo_path:
            continue

        desc_el = article.select_one("p")
        lang_el = article.select_one("[itemprop='programmingLanguage']")
        total_star_el = article.select_one("a.Link--muted")
        period_star_el = article.select_one("span.d-inline-block.float-sm-right")

        def _int(text: str | None) -> int:
            if not text:
                return 0
            digits = "".join(ch for ch in text if ch.isdigit())
            return int(digits) if digits else 0

        repos.append({
            "repo": repo_path,
            "url": f"https://github.com/{repo_path}",
            "description": desc_el.get_text(strip=True)[:200] if desc_el else "",
            "language": lang_el.get_text(strip=True) if lang_el else "",
            "total_stars": _int(total_star_el.get_text() if total_star_el else ""),
            "period_stars": _int(period_star_el.get_text() if period_star_el else ""),
        })
    return repos


def collect_trending(settings: dict | None = None) -> list[dict]:
    cfg = settings or load_settings()
    tcfg = cfg["trending"]
    seen, merged = set(), []
    for lang in tcfg.get("languages", [""]) or [""]:
        url = "https://github.com/trending"
        if lang:
            url += f"/{lang}"
        url += f"?since={tcfg.get('since', 'daily')}"
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            repos = _parse_trending(resp.text)
            print(f"  [OK] trending/{lang or 'all'}: {len(repos)}개")
            for r in repos[:tcfg.get("limit", 6)]:
                key = r["repo"]
                if key not in seen:
                    seen.add(key)
                    merged.append(r)
        except Exception as e:
            print(f"  [SKIP] GitHub trending({lang or 'all'}) 실패(무시됨): {e}")
    return merged


if __name__ == "__main__":
    print("[테스트] Trending 수집기 단독 실행")
    result = collect_trending()
    for r in result[:3]:
        print(f" - {r['repo']} ★{r['total_stars']} (+{r['period_stars']} 오늘)")
