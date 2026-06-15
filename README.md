# Dodo Munger Scanner

Dashboard that replicates the AskLivermore **"Munger 200W | Charlie Munger"**
stock scanner and enriches it with a derived **Munger Score**, fundamental
analysis (rules-of-thumb), **Snowflake** profiles and weekly candlestick charts.

Built on the **WAT framework** (Workflows, Agents, Tools): probabilistic AI
orchestrates, deterministic Python scripts execute. See [CLAUDE.md](CLAUDE.md).

## Features

- 📋 Full scanner table (defaults to AskLivermore order: market cap desc), with
  search and rich numeric filters (ROE/margin/growth/PE/PB/DE/current ratio…).
- 🎩 **Munger Score** = 65 % Quality + 35 % Value (percentile-based) — `tools/enrich.py`.
- 📄 **Doc score** = % of your fundamental rules passed (P/E, ROE, D/E, current
  ratio, revenue/EPS growth, payout, P/B, FCF) — `tools/doc_analysis.py`.
- 🔍 Click a row → per-stock detail: SimplyWall.st-style Snowflake, strengths/risks,
  weekly candlestick (50w/200w MA) and a direct TradingView chart link.

## Architecture

| Layer | Where | Role |
|-------|-------|------|
| Workflows | `workflows/*.md` | Plain-language SOPs |
| Agent | the AI | Orchestration |
| Tools | `tools/*.py` | Deterministic execution (fetch, enrich, external data) |

Data source: public endpoint `GET asklivermore.com/api/scanners/<id>/results`
(no auth). External fundamentals + weekly prices via `yfinance`.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On first launch the app auto-downloads the scanner data into `.tmp/`. The
"🔄 Aggiorna dati scanner" button refreshes it; "📥 Scarica fondamentali"
fetches yfinance ratios (cached 7 days).

## Deploy on Streamlit Community Cloud (free)

1. Push this repo to GitHub (see below).
2. Go to **share.streamlit.io** and sign in with GitHub.
3. **New app** → pick this repo, branch `main`, main file `app.py` → **Deploy**.
4. You get a public URL (e.g. `https://<app>.streamlit.app`) to share with friends.

No secrets are required — the scanner API is public and `.env` is gitignored.
The app fetches fresh data on startup, so each deploy/restart is up to date.

## Project layout

```
app.py                  # Streamlit dashboard (UI only)
tools/                  # deterministic scripts
  fetch_scanner.py      # download scanner -> .tmp
  enrich.py             # Munger Score
  external.py           # yfinance fundamentals + weekly OHLC (cached)
  doc_analysis.py       # fundamental rules + Snowflake axes
workflows/              # SOPs
.streamlit/config.toml  # dark theme
.tmp/                   # disposable cache (gitignored)
```
