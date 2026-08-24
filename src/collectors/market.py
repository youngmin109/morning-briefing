"""시세 수집기 — 국내주식(pykrx) + 해외주식/환율(yfinance) + 코인(업비트 공개API).

모든 소스는 인증 없이 접근 가능한 것만 사용한다 (키 등록 불필요).
"""
from datetime import datetime, timedelta, timezone

import requests

from src.common import load_settings, kst_now

COIN_LABELS = {
    "KRW-BTC": "비트코인", "KRW-ETH": "이더리움", "KRW-SOL": "솔라나",
    "KRW-XRP": "리플", "KRW-DOGE": "도지코인",
}


def _pct(new: float, old: float) -> float:
    if not old:
        return 0.0
    return round((new - old) / old * 100, 2)


def _fetch_kr(settings: dict) -> dict:
    from pykrx import stock  # 지연 import: 무거운 pandas 의존성은 필요할 때만

    cfg = settings["market"]
    today = kst_now()
    start = (today - timedelta(days=cfg.get("history_days", 5) * 2)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    stocks = []
    for item in cfg["kr_stocks"]:
        label = item["label"]
        try:
            df = stock.get_market_ohlcv(start, end, item["code"])
            if df is None or len(df) < 2:
                continue
            prev_close, close = float(df["종가"].iloc[-2]), float(df["종가"].iloc[-1])
            chg = _pct(close, prev_close)
            stocks.append({"label": label, "code": item["code"], "price": int(close), "change_pct": chg})
            print(f"  [OK] {label}: {int(close):,}원 ({chg:+.2f}%)")
        except Exception as e:
            print(f"  [SKIP] KRX 종목 {label}: {e}")
    return {"stocks": stocks}


def _fetch_yfinance(settings: dict) -> dict:
    """해외주식 + 환율 + 국내지수(코스피/코스닥 — pykrx 지수는 KRX 로그인 필요해서 yfinance 사용)."""
    import yfinance as yf

    cfg = settings["market"]
    buckets = {"stocks": [], "fx": [], "indices": []}
    targets = (
        [(item, "stocks") for item in cfg["us_tickers"]]
        + [(item, "fx") for item in cfg["fx_tickers"]]
        + [(item, "indices") for item in cfg["kr_indices"]]
    )
    for item, group in targets:
        ticker_str = item.get("ticker") or item.get("code")
        label = item["label"]
        try:
            hist = yf.Ticker(ticker_str).history(period="7d")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                print(f"  [SKIP] {label}: 데이터 부족")
                continue
            price = float(closes.iloc[-1])
            chg = _pct(price, float(closes.iloc[-2]))
            rounded = round(price, 2)
            buckets[group].append({"label": label, "ticker": ticker_str, "price": rounded, "change_pct": chg})
            print(f"  [OK] {label}: {rounded} ({chg:+.2f}%)")
        except Exception as e:
            print(f"  [SKIP] {ticker_str}({label}): {e}")
    return buckets


def _fetch_coins(settings: dict) -> list[dict]:
    cfg = settings["market"]["coins"]
    url = f"https://api.upbit.com/v1/ticker?markets={','.join(cfg)}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    coins = []
    for t in resp.json():
        market = t["market"]
        price = t["trade_price"]
        change_pct = round(t["signed_change_rate"] * 100, 2)
        coins.append({
            "label": COIN_LABELS.get(market, market),
            "market": market,
            "price": int(price),
            "change_pct": change_pct,
        })
        print(f"  [OK] {COIN_LABELS.get(market, market)}: {int(price):,}원 ({change_pct:+.2f}%)")
    return coins


def collect_market(settings: dict | None = None) -> dict:
    cfg = settings or load_settings()
    print("  [국내 종목(pykrx)]")
    kr = _fetch_kr(cfg)
    print("  [지수/해외 주식/환율(yfinance)]")
    yf_result = _fetch_yfinance(cfg)
    kr["indices"] = yf_result.pop("indices", [])
    print("  [코인(업비트)]")
    crypto = _fetch_coins(cfg)
    return {
        "kr": kr,
        "us": {"stocks": yf_result.get("stocks", []), "fx": yf_result.get("fx", [])},
        "crypto": crypto,
        "collected_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
    }


if __name__ == "__main__":
    print("[테스트] 시세 수집기 단독 실행")
    result = collect_market()
    n = sum(len(v) if isinstance(v, list) else sum(len(x) for x in v.values()) for v in result.values() if isinstance(v, (list, dict)))
    print(f"완료: 항목 {n}개")
