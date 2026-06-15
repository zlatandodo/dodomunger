# Workflow: Fetch Munger 200W Scanner (AskLivermore)

## Objective
Pull the "Munger 200W | Charlie Munger" scanner results from AskLivermore into
local files so we can replicate the database and enrich it with extra analysis.
"Wonderful businesses near their 200-week moving average value zone."

## Trigger / When to run
Weekly (after market close — site updates daily after close), or on demand.

## Data source / API
- **Endpoint:** `GET https://www.asklivermore.com/api/scanners/<scanner_id>/results`
- **Scanner id:** `munger-200w`
- **Auth:** NONE required. The results endpoint is public — returns 200 without
  any token or cookie. (The app itself authenticates via Supabase
  `sb-...-auth-token` in localStorage, but the results API does not need it.)
- **Discovery:** found via the gallery at `/#/gallery` → search "Munger" → RUN,
  which loads `/#/scanner/munger-200w` and fires the API call above.
- **Other scanners:** the gallery has 53 scanners, all under the same
  `/api/scanners/<id>/results` path — the tool is generic via `scanner_id`.

### Response shape
```
{ count, sort_by, sort_dir, scanner_id, matches: [ {...32 fields...} ] }
```
NOTE: server-side `sort_by` / `sort_dir` query params are IGNORED — the API
always returns market_cap desc. Sort and filter downstream (Python).

### The 32 fields per stock
- **Identity:** ticker, name, sector, tv_symbol (e.g. "NASDAQ:MSFT"),
  ticker_type ("CS"=common stock), market_cap, shares_out
- **Price/MA:** price, matched_close, ma200w, pct_from_200w, ma_period_weeks
  (=200), ma_slope (often null), change_pct
- **Volume:** day_volume, avg_vol_50
- **Quality / fundamentals:** quality (letter grade e.g. "A+"), roe,
  profit_margin, revenue_growth, fa_rating (fundamental, ~0-10)
- **Technical ratings:** rs_rating (relative strength), ta_rating
- **Index membership:** in_sp500, in_nasdaq100, in_russell2000 (booleans)
- **Options:** has_options, has_weekly_options (booleans)
- **Short data:** short_volume, short_volume_ratio, short_date
- **Meta:** matched_date

## Tools used
- `tools/fetch_scanner.py` — GETs the endpoint, writes raw JSON + flat CSV to `.tmp/`.
  - `python tools/fetch_scanner.py` (defaults to munger-200w)
  - `python tools/fetch_scanner.py <scanner_id> --out .tmp`
  - Sends browser-like User-Agent/Referer/Origin headers (endpoint is public but
    this guards against host-side gating).
- `tools/enrich.py` — reads the raw JSON, adds a derived **Munger Score**
  (65% quality + 35% value, percentile-based) plus quality_score/value_score/
  munger_rank; writes `.tmp/<id>_enriched.{json,csv}`.
- `app.py` — Streamlit dashboard reading the enriched JSON (filters, ranking,
  per-stock detail, charts, CSV export, "Aggiorna dati" button that re-runs the
  fetch+enrich pipeline).

## Steps
1. Run `python tools/fetch_scanner.py munger-200w`.
2. Run `python tools/enrich.py munger-200w`.
3. Launch dashboard: `python -m streamlit run app.py` (or `./run_dashboard.ps1`).
   In the app, the "🔄 Aggiorna dati" button runs steps 1-2 for you.

## Expected outputs
- `.tmp/munger-200w_results.{json,csv}` — raw, 359 rows × 32 cols (varies weekly).
- `.tmp/munger-200w_enriched.{json,csv}` — + munger_score/quality_score/
  value_score/munger_rank.
- Local web dashboard at http://localhost:8501 (default Streamlit port).

## Edge cases & failure handling
- HTTP 403/blocked from Python: re-add/adjust headers; worst case fall back to
  the Supabase bearer token from the browser session. (As of first build the raw
  GET works without auth.)
- `matches` key missing -> tool raises ValueError (API shape changed).
- Empty `sector` exists for some rows — handle "" as Unknown in any grouping.

## Notes / lessons learned
- Verified 2026-06-15: raw `requests.get` (no auth) returns 359 matches. Works.
- Dashboard target (Google Sheets vs local web app) and the desired "extra info"
  enrichment are NOT yet decided — confirm with the user before building layer 2.
