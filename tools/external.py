"""external.py — Fetch external data (yfinance) for scanner tickers, with caching.

Provides two things the AskLivermore scanner doesn't:
  - Fundamental ratios needed by FUNDAMENTAL ANALYSIS.docx (P/E, P/B, D/E,
    current ratio, payout, FCF, EPS growth, dividend yield, ...).
  - Weekly OHLC history (+ 50w / 200w SMA) for charting.

Caching keeps it cheap to re-open the dashboard:
  - Fundamentals: .tmp/fundamentals/<TICKER>.json  (TTL 7 days)
  - Weekly OHLC:  .tmp/weekly/<TICKER>.csv          (TTL 1 day)

CLI (batch pre-fetch fundamentals for the whole scanner universe):
    python tools/external.py --all
    python tools/external.py --tickers MSFT,AAPL,BRK.B
    python tools/external.py --all --max-age-days 7
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

FUND_DIR = os.path.join(".tmp", "fundamentals")
WEEKLY_DIR = os.path.join(".tmp", "weekly")

FUND_KEYS = [
    "trailingPE", "forwardPE", "priceToBook", "debtToEquity", "currentRatio",
    "quickRatio", "payoutRatio", "freeCashflow", "operatingCashflow",
    "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
    "dividendYield", "returnOnEquity", "returnOnAssets", "profitMargins",
    "trailingEps", "forwardEps", "marketCap", "longName", "sector", "industry",
]


def normalize_ticker(t: str) -> str:
    """AskLivermore tickers -> yfinance symbols (class shares use '-')."""
    return str(t).strip().upper().replace(".", "-")


def _fresh(path: str, max_age_days: float) -> bool:
    if not os.path.exists(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < max_age_days * 86400


def fetch_fundamentals(ticker: str, max_age_days: float = 7,
                       force: bool = False) -> dict:
    """Return a dict of fundamental metrics for `ticker`, using a 7-day cache."""
    os.makedirs(FUND_DIR, exist_ok=True)
    sym = normalize_ticker(ticker)
    path = os.path.join(FUND_DIR, f"{sym}.json")
    if not force and _fresh(path, max_age_days):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    import yfinance as yf
    out = {"ticker": ticker, "yf_symbol": sym,
           "_fetched_at": datetime.now(timezone.utc).isoformat()}
    try:
        info = yf.Ticker(sym).info or {}
        for k in FUND_KEYS:
            out[k] = info.get(k)
        out["_ok"] = bool(info.get("marketCap") or info.get("trailingPE")
                          or info.get("longName"))
    except Exception as e:  # noqa: BLE001
        out["_ok"] = False
        out["_error"] = f"{type(e).__name__}: {e}"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out


def fetch_weekly(ticker: str, period: str = "max", max_age_days: float = 1):
    """Return a list of weekly bars [{date, open, high, low, close, volume,
    sma50, sma200}], cached as CSV for a day. Requires pandas.
    """
    import pandas as pd
    os.makedirs(WEEKLY_DIR, exist_ok=True)
    sym = normalize_ticker(ticker)
    path = os.path.join(WEEKLY_DIR, f"{sym}.csv")
    if _fresh(path, max_age_days):
        df = pd.read_csv(path)
        return df.to_dict("records")

    import yfinance as yf
    h = yf.Ticker(sym).history(period=period, interval="1wk")
    if h is None or h.empty:
        return []
    df = h[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df["sma50"] = df["close"].rolling(50).mean().round(2)
    df["sma200"] = df["close"].rolling(200).mean().round(2)
    df = df.round({"open": 2, "high": 2, "low": 2, "close": 2})
    df.index = df.index.tz_localize(None)
    df.insert(0, "date", df.index.strftime("%Y-%m-%d"))
    df.to_csv(path, index=False)
    return df.to_dict("records")


def _load_universe_tickers(scanner_id="munger-200w"):
    src = os.path.join(".tmp", f"{scanner_id}_results.json")
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    return [m["ticker"] for m in data["matches"]]


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-fetch yfinance fundamentals.")
    ap.add_argument("--all", action="store_true", help="all tickers in the scanner")
    ap.add_argument("--tickers", help="comma-separated ticker list")
    ap.add_argument("--scanner", default="munger-200w")
    ap.add_argument("--max-age-days", type=float, default=7)
    ap.add_argument("--sleep", type=float, default=0.4, help="delay between calls")
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    elif args.all:
        tickers = _load_universe_tickers(args.scanner)
    else:
        print("[error] pass --all or --tickers", file=sys.stderr)
        return 1

    ok = 0
    for i, t in enumerate(tickers, 1):
        d = fetch_fundamentals(t, max_age_days=args.max_age_days)
        ok += 1 if d.get("_ok") else 0
        cached = "cache" if d.get("_fetched_at", "") and _fresh(
            os.path.join(FUND_DIR, normalize_ticker(t) + ".json"), args.max_age_days) else "live"
        print(f"[{i}/{len(tickers)}] {t:8} ok={d.get('_ok')} "
              f"PE={d.get('trailingPE')} PB={d.get('priceToBook')}")
        if i < len(tickers):
            time.sleep(args.sleep)
    print(f"[done] {ok}/{len(tickers)} fetched ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
