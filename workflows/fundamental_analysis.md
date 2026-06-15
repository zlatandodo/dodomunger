# Workflow: Fundamental Analysis (FUNDAMENTAL ANALYSIS.docx rules)

## Objective
Evaluate scanner stocks against the user's fundamental-analysis methodology and
enrich them with valuation data + weekly charts the scanner doesn't provide.

## Source methodology
A personal fundamental-analysis methodology doc (kept locally, not in the repo).
12 rules of thumb; the machine-checkable ones are encoded in `tools/doc_analysis.py`:

| # | Metric | Rule of thumb | Source field |
|---|--------|---------------|--------------|
| 1 | P/E | 15-20 ragionevole; basso = sottovalutato (pass ≤20) | yfinance trailingPE |
| 6 | ROE | ≥ 15% | scanner `roe` (fallback yfinance returnOnEquity) |
| 2 | Debt/Equity | < 1 | yfinance debtToEquity (÷100 — it's a percent) |
| 3 | Current ratio | ≥ 2 | yfinance currentRatio |
| 4 | Revenue growth | positiva/consistente (pass >0) | scanner `revenue_growth` / yfinance |
| 5 | EPS growth | in crescita (pass >0) | yfinance earningsGrowth |
| 7 | Dividend payout | < 60% (solo se paga dividendo) | yfinance payoutRatio |
| 8 | P/B | < 1 = sottovalutato | yfinance priceToBook |
| 9 | Free cash flow | positivo | yfinance freeCashflow |

Rules 10-12 (growth vs value, diversification, industry comparison) are
portfolio/context judgments, not per-stock booleans — not auto-scored.

**Doc score** = % of *applicable* rules passed. Stocks without downloaded
fundamentals are scored only on the scanner-derived rules (ROE, revenue growth).

## Tools used
- `tools/external.py` — yfinance fetch with caching:
  - `fetch_fundamentals(ticker)` → `.tmp/fundamentals/<TICKER>.json` (TTL 7d)
  - `fetch_weekly(ticker)` → weekly OHLC + 50w/200w SMA (cached CSV, TTL 1d)
  - CLI batch: `python tools/external.py --all` (all scanner tickers, ~0.4s each)
    or `python tools/external.py --tickers MSFT,AON`.
- `tools/doc_analysis.py` — pure rule-evaluation logic (`evaluate(merged_dict)`).
- `app.py` — dashboard surfaces it all: numeric filters (ROE/margin/growth min,
  P/E/PB/DE max, current-ratio min, doc-score min), per-stock weekly candlestick
  chart, and a per-stock rule checklist (✅/❌/— with values vs thresholds).
  SimplyWall.st-inspired UI: dark theme (`.streamlit/config.toml`), a 5-axis
  **Snowflake** radar (Value/Future/Past/Health/Dividend via
  `doc_analysis.snowflake_axes`) and Rewards/Risks lists in the detail tab.
  Table defaults to AskLivermore order (market_cap desc); sort control is at the
  top with a visible "Ordinato per …" caption. (The old generic "Grafici" tab
  was removed — it added little.)

## Steps
1. Ensure scanner data exists (see `fetch_munger_scanner.md`).
2. Download fundamentals: in the app click "📥 Scarica fondamentali (filtrati)"
   for the current selection, or run `python tools/external.py --all` once/week
   to enable doc-analysis filtering across the whole universe (~2-3 min, cached).
3. Weekly charts are fetched on demand per stock in the Detail tab (cached daily).

## Edge cases & failure handling
- yfinance ticker mismatch: class shares use '-' not '.' — `normalize_ticker`
  handles `BRK.B`→`BRK-B`. Some tickers may still return empty info (`_ok=False`).
- yfinance `debtToEquity` is a PERCENT; divide by 100 for the "< 1" rule.
- NaN/missing values are treated as "not applicable" (—), never as a failed rule.
- yfinance rate limits: keep the 0.4s inter-call delay in batch mode; results are
  cached 7 days so re-runs are cheap.

## Notes / lessons learned
- Verified 2026-06-15: P/E, P/B, D/E, current ratio, payout, FCF, EPS growth,
  ROE, weekly OHLC all available from yfinance `.info` / `.history`.
- 200w SMA from yfinance (~381 for MSFT) closely matches scanner `ma200w` (~386);
  small diffs are data-source/timing, expected.
