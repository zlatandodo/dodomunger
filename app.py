"""Dodo Munger Scanner — Streamlit dashboard.

Replicates the AskLivermore "Munger 200W | Charlie Munger" database locally and
adds:
  - a derived Munger Score (tools/enrich.py),
  - fundamental analysis vs FUNDAMENTAL ANALYSIS.docx rules (tools/doc_analysis.py)
    using yfinance data (tools/external.py),
  - weekly candlestick charts with 50w / 200w moving averages,
  - rich numeric filtering (e.g. ROE above X%).

Run:  streamlit run app.py
"""
import glob
import json
import os
import subprocess
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
import doc_analysis  # noqa: E402
import external  # noqa: E402

SCANNER_ID = "munger-200w"
TMP = ".tmp"
ENRICHED = os.path.join(TMP, f"{SCANNER_ID}_enriched.json")
FUND_DIR = os.path.join(TMP, "fundamentals")          # fresh cache (gitignored)
SEED_FUND_DIR = os.path.join("data", "fundamentals")  # committed snapshot
FUND_DIRS = [SEED_FUND_DIR, FUND_DIR]                 # later dir overrides earlier

st.set_page_config(page_title="Dodo Munger Scanner", page_icon="🎩", layout="wide")

NUMERIC_COLS = [
    "munger_score", "quality_score", "value_score", "munger_rank",
    "price", "matched_close", "ma200w", "pct_from_200w", "change_pct",
    "roe", "profit_margin", "revenue_growth", "fa_rating", "rs_rating",
    "ta_rating", "market_cap", "day_volume", "avg_vol_50",
    "short_volume", "short_volume_ratio", "shares_out",
]
# External (yfinance) columns merged in from the fundamentals cache.
EXT_COLS = ["trailingPE", "forwardPE", "priceToBook", "debtToEquity",
            "currentRatio", "payoutRatio", "freeCashflow", "earningsGrowth",
            "dividendYield", "returnOnEquity"]


def pv(x):
    if x is None or (not isinstance(x, (list, dict)) and pd.isna(x)):
        return None
    return x.item() if hasattr(x, "item") else x


def run_pipeline():
    log = []
    for cmd in ([sys.executable, "tools/fetch_scanner.py", SCANNER_ID],
                [sys.executable, "tools/enrich.py", SCANNER_ID]):
        p = subprocess.run(cmd, capture_output=True, text=True)
        log.append(p.stdout + p.stderr)
        if p.returncode != 0:
            return False, "\n".join(log)
    return True, "\n".join(log)


@st.cache_data(show_spinner=False)
def load_fundamentals(_sig):
    """Load yfinance fundamentals into {ticker: dict}.

    Reads the committed seed snapshot first, then the fresh .tmp cache, so a
    freshly-downloaded ticker overrides the bundled one.
    """
    out = {}
    for d_dir in FUND_DIRS:
        for path in glob.glob(os.path.join(d_dir, "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("ticker"):
                    out[d["ticker"]] = d
            except Exception:  # noqa: BLE001
                continue
    return out


@st.cache_data(show_spinner=False)
def load_data(path, _mtime, _fund_sig):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data["matches"])
    funds = load_fundamentals(_fund_sig)

    # merge external columns + document analysis per row
    ext_rows, doc_rows = [], []
    for _, r in df.iterrows():
        fund = funds.get(r["ticker"], {})
        ext_rows.append({c: fund.get(c) for c in EXT_COLS})
        merged = {**r.to_dict(), **fund}
        res = doc_analysis.evaluate(merged)
        doc_rows.append({
            "doc_score": res["doc_score"],
            "doc_passed": res["passed"],
            "doc_applicable": res["applicable"],
            "has_fund": bool(fund.get("_ok")),
        })
    df = pd.concat([df, pd.DataFrame(ext_rows), pd.DataFrame(doc_rows)], axis=1)

    for c in NUMERIC_COLS + EXT_COLS + ["doc_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["de_ratio"] = df["debtToEquity"] / 100.0           # yfinance D/E is percent
    df["sector"] = df["sector"].replace("", "Unknown").fillna("Unknown")
    df["market_cap_b"] = df["market_cap"] / 1e9
    meta = {k: data.get(k) for k in ("count", "scanner_id", "_fetched_at")}
    meta["n_fund"] = sum(1 for v in funds.values() if v.get("_ok"))
    return df, meta


def fund_signature():
    """Cheap signature that changes when either fundamentals dir changes."""
    files = []
    for d_dir in FUND_DIRS:
        files += glob.glob(os.path.join(d_dir, "*.json"))
    return (len(files), round(max((os.path.getmtime(f) for f in files), default=0), 2))


# ---------------------------------------------------------------- data load
if not os.path.exists(ENRICHED):
    st.warning("Nessun dato locale. Scarico dallo scanner AskLivermore…")
    ok, log = run_pipeline()
    if not ok:
        st.error("Download fallito:\n\n" + log)
        st.stop()

df, meta = load_data(ENRICHED, os.path.getmtime(ENRICHED), fund_signature())

# ---------------------------------------------------------------- sidebar
st.sidebar.title("🎩 Dodo Munger Scanner")
if st.sidebar.button("🔄 Aggiorna dati scanner", use_container_width=True):
    with st.spinner("Aggiorno dallo scanner…"):
        ok, log = run_pipeline()
    if ok:
        st.cache_data.clear()
        st.sidebar.success("Dati aggiornati.")
        st.rerun()
    else:
        st.sidebar.error("Errore:\n" + log)

st.sidebar.caption(f"Ultimo fetch: {meta.get('_fetched_at', 'n/d')}")
st.sidebar.caption(f"Fondamentali yfinance in cache: {meta.get('n_fund', 0)}/{len(df)}")
st.sidebar.divider()

search = st.sidebar.text_input("🔎 Cerca ticker / nome").strip().lower()

sectors = sorted(df["sector"].unique())
sel_sectors = st.sidebar.multiselect("Settore (GICS)", sectors, default=sectors)

grade_order = "A+ A A- B+ B B- C+ C C- D F".split()
grades = sorted(df["quality"].dropna().unique(),
                key=lambda g: grade_order.index(g) if g in grade_order else 99)
sel_grades = st.sidebar.multiselect("Quality grade", grades, default=grades)

st.sidebar.subheader("📐 Filtri numerici (scanner)")
st.sidebar.caption("Es.: ROE sopra il 15%. I default mostrano tutti i titoli.")


def _floor(col):
    v = df[col].min()
    return float(int(v) - 1) if pd.notna(v) else 0.0


roe_min = st.sidebar.number_input("ROE minimo %", value=_floor("roe"), step=1.0)
pm_min = st.sidebar.number_input("Profit margin minimo %",
                                 value=_floor("profit_margin"), step=1.0)
rg_min = st.sidebar.number_input("Revenue growth minimo %",
                                 value=_floor("revenue_growth"), step=1.0)
score_min = st.sidebar.slider("Munger Score minimo", 0, 100, 0)
mc_max = float(df["market_cap_b"].max())
mc_range = st.sidebar.slider("Market Cap (miliardi $)", 0.0, round(mc_max, 1),
                             (0.0, round(mc_max, 1)))
zone = st.sidebar.slider("Distanza dalla MA200w (%)", -50, 100, (-50, 100),
                         help="Negativo = sotto la media (più 'value')")

st.sidebar.subheader("💰 Filtri fondamentali (doc / yfinance)")
st.sidebar.caption("Attivi solo sui titoli con fondamentali scaricati.")
use_fund = st.sidebar.checkbox("Solo titoli con fondamentali")
pe_max = st.sidebar.number_input("P/E massimo (0 = off)", value=0.0, step=1.0)
pb_max = st.sidebar.number_input("P/B massimo (0 = off)", value=0.0, step=0.5)
de_max = st.sidebar.number_input("Debt/Equity massimo (0 = off)", value=0.0, step=0.5)
cr_min = st.sidebar.number_input("Current ratio minimo (0 = off)", value=0.0, step=0.5)
docscore_min = st.sidebar.slider("Doc score minimo (regole superate %)", 0, 100, 0)

st.sidebar.divider()
idx_opts = st.sidebar.multiselect("Indice", ["S&P 500", "Nasdaq 100", "Russell 2000"])
only_options = st.sidebar.checkbox("Solo con opzioni")

# ---------------------------------------------------------------- filtering
f = df.copy()
if search:
    f = f[f["ticker"].str.lower().str.contains(search) |
          f["name"].str.lower().str.contains(search)]
f = f[f["sector"].isin(sel_sectors) & f["quality"].isin(sel_grades)]
# min filters keep rows with missing data visible (only exclude values below min)
f = f[f["roe"].isna() | (f["roe"] >= roe_min)]
f = f[f["profit_margin"].isna() | (f["profit_margin"] >= pm_min)]
f = f[f["revenue_growth"].isna() | (f["revenue_growth"] >= rg_min)]
f = f[f["munger_score"].fillna(-1) >= score_min]
f = f[(f["market_cap_b"] >= mc_range[0]) & (f["market_cap_b"] <= mc_range[1])]
f = f[(f["pct_from_200w"] >= zone[0]) & (f["pct_from_200w"] <= zone[1])]
if use_fund:
    f = f[f["has_fund"]]
if pe_max > 0:
    f = f[f["trailingPE"].notna() & (f["trailingPE"] > 0) & (f["trailingPE"] <= pe_max)]
if pb_max > 0:
    f = f[f["priceToBook"].notna() & (f["priceToBook"] <= pb_max)]
if de_max > 0:
    f = f[f["de_ratio"].notna() & (f["de_ratio"] <= de_max)]
if cr_min > 0:
    f = f[f["currentRatio"].notna() & (f["currentRatio"] >= cr_min)]
if docscore_min > 0:
    f = f[f["doc_score"].fillna(-1) >= docscore_min]
if "S&P 500" in idx_opts:
    f = f[f["in_sp500"] == True]  # noqa: E712
if "Nasdaq 100" in idx_opts:
    f = f[f["in_nasdaq100"] == True]  # noqa: E712
if "Russell 2000" in idx_opts:
    f = f[f["in_russell2000"] == True]  # noqa: E712
if only_options:
    f = f[f["has_options"] == True]  # noqa: E712

# ---------------------------------------------------------------- header
st.title("Dodo Munger Scanner")
st.caption("Wonderful businesses near their 200-week MA value zone — replica "
           "AskLivermore + Munger Score + analisi fondamentale (regole del tuo documento).")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Titoli (filtrati)", f"{len(f)} / {len(df)}")
c2.metric("Munger Score medio", f"{f['munger_score'].mean():.1f}" if len(f) else "–")
c3.metric("ROE mediano", f"{f['roe'].median():.1f}%" if len(f) else "–")
ff = f[f["has_fund"]] if "has_fund" in f else f.iloc[0:0]
c4.metric("Doc score medio", f"{ff['doc_score'].mean():.0f}%" if len(ff) else "–",
          help="Media sui titoli con fondamentali yfinance scaricati.")

# fundamentals fetch action
fa, fb = st.columns([3, 1])
fa.caption("Per usare i filtri/analisi fondamentali serve scaricare i dati yfinance "
           "dei titoli (cache 7 giorni).")
if fb.button("📥 Scarica fondamentali (filtrati)", use_container_width=True):
    tickers = f["ticker"].tolist()
    prog = st.progress(0.0, text="Scarico fondamentali…")
    for i, tk in enumerate(tickers, 1):
        external.fetch_fundamentals(tk)
        prog.progress(i / max(len(tickers), 1), text=f"{tk} ({i}/{len(tickers)})")
    prog.empty()
    st.cache_data.clear()
    st.success(f"Fondamentali aggiornati per {len(tickers)} titoli.")
    st.rerun()

def plotly_dark(fig, height):
    fig.update_layout(height=height, template="plotly_dark",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=0, r=0, t=10, b=0))
    return fig


# ---------------------------------------------------------------- table
if True:
    # Sort controls kept at the top so the ordering is always visible.
    # Default mirrors AskLivermore: Market Cap, descending.
    SORT_LABELS = {
        "market_cap": "Market Cap (come AskLivermore)", "munger_score": "Munger Score",
        "doc_score": "Doc score", "quality_score": "Qualità", "value_score": "Value",
        "roe": "ROE", "profit_margin": "Profit margin", "revenue_growth": "Revenue growth",
        "trailingPE": "P/E", "priceToBook": "P/B", "pct_from_200w": "% da MA200w",
        "change_pct": "Variazione %",
    }
    sc1, sc2 = st.columns([3, 1])
    sort_col = sc1.selectbox("Ordina per", list(SORT_LABELS),
                             format_func=lambda k: SORT_LABELS[k], index=0)
    direction = sc2.radio("Direzione", ["Decrescente", "Crescente"], horizontal=True)
    asc = direction == "Crescente"
    arrow = "▲" if asc else "▼"
    st.caption(f"Ordinato per **{SORT_LABELS[sort_col]}** {arrow} · {len(f)} titoli")
    show = f.sort_values(sort_col, ascending=asc, na_position="last")

    cols = ["munger_rank", "ticker", "name", "sector", "quality", "munger_score",
            "doc_score", "price", "ma200w", "pct_from_200w", "roe", "profit_margin",
            "revenue_growth", "trailingPE", "priceToBook", "de_ratio",
            "currentRatio", "market_cap_b", "change_pct"]
    cols = [c for c in cols if c in show.columns]
    st.caption("💡 Clicca una riga (ticker / nome) per aprire il dettaglio sotto la tabella.")
    event = st.dataframe(
        show[cols], use_container_width=True, hide_index=True, height=460,
        key="tbl", on_select="rerun", selection_mode="single-row",
        column_config={
            "munger_rank": st.column_config.NumberColumn("#", width="small"),
            "munger_score": st.column_config.ProgressColumn(
                "Munger", min_value=0, max_value=100, format="%.1f"),
            "doc_score": st.column_config.NumberColumn("Doc %", format="%.0f"),
            "market_cap_b": st.column_config.NumberColumn("Mkt Cap ($B)", format="%.1f"),
            "pct_from_200w": st.column_config.NumberColumn("% da MA200w", format="%.1f"),
            "roe": st.column_config.NumberColumn("ROE %", format="%.1f"),
            "profit_margin": st.column_config.NumberColumn("Margin %", format="%.1f"),
            "revenue_growth": st.column_config.NumberColumn("Rev Gr %", format="%.1f"),
            "trailingPE": st.column_config.NumberColumn("P/E", format="%.1f"),
            "priceToBook": st.column_config.NumberColumn("P/B", format="%.2f"),
            "de_ratio": st.column_config.NumberColumn("D/E", format="%.2f"),
            "currentRatio": st.column_config.NumberColumn("Curr.R", format="%.2f"),
            "change_pct": st.column_config.NumberColumn("Chg %", format="%.2f"),
        },
    )
    st.download_button("⬇️ Scarica CSV (filtrato)",
                       show[cols].to_csv(index=False).encode("utf-8"),
                       file_name="munger_filtered.csv", mime="text/csv")

# ---------------------------------------------------------------- detail
def render_detail(tkr):
    if True:
      if True:
        row = f[f["ticker"] == tkr].iloc[0]
        fund = load_fundamentals(fund_signature()).get(tkr, {})
        merged = {**row.to_dict(), **fund}
        res = doc_analysis.evaluate(merged)
        axes = doc_analysis.snowflake_axes(merged)

        # ---- header ----
        st.subheader(f"{row['ticker']} · {row['name']}")
        st.caption(f"{row['sector']} · quality {row['quality']}")
        h1, h2, h3, h4, h5 = st.columns(5)
        h1.metric("Munger Score", f"{pv(row['munger_score'])}")
        h2.metric("Prezzo", f"{pv(row['price']):.2f}", f"{pv(row['change_pct']):.2f}%")
        h3.metric("MA200w", f"{pv(row['ma200w']):.2f}")
        h4.metric("% da MA200w", f"{pv(row['pct_from_200w']):.1f}%")
        h5.metric("Doc score", f"{pv(row['doc_score'])}%"
                  if pd.notna(row["doc_score"]) else "n/d")

        # transparent breakdown of both scores for THIS stock
        qs, vs = pv(row.get("quality_score")), pv(row.get("value_score"))
        st.caption(
            f"🎩 **Munger {pv(row['munger_score'])}** = 65% · Qualità {qs} "
            f"+ 35% · Value {vs}  ·  "
            f"📄 **Doc {pv(row['doc_score'])}%** = {res['passed']}/{res['applicable']} "
            f"regole del documento superate")

        # ---- snowflake + rewards/risks (SimplyWall.st-inspired) ----
        cL, cR = st.columns([1, 1])
        with cL:
            st.markdown("**Snowflake**")
            cats = ["Value", "Future", "Past", "Health", "Dividend"]
            vals = [axes[c] if axes[c] is not None else 0 for c in cats]
            radar = go.Figure(go.Scatterpolar(
                r=vals + [vals[0]], theta=cats + [cats[0]], fill="toself",
                fillcolor="rgba(45,212,167,0.45)", line_color="#2dd4a7",
                hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>"))
            radar.update_layout(
                polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False,
                                           gridcolor="#30363d"),
                           angularaxis=dict(gridcolor="#30363d")),
                showlegend=False)
            st.plotly_chart(plotly_dark(radar, 320), use_container_width=True)
        with cR:
            rewards = [doc_analysis.RULE_REWARD_LABEL[r["key"]]
                       for r in res["rules"] if r["ok"] is True]
            risks = [doc_analysis.RULE_RISK_LABEL[r["key"]]
                     for r in res["rules"] if r["ok"] is False]
            st.markdown("**✅ Punti di forza**")
            st.markdown("\n".join(f"- {x}" for x in rewards) or "_nessuno_")
            st.markdown("**⚠️ Rischi / debolezze**")
            st.markdown("\n".join(f"- {x}" for x in risks) or "_nessuno_")
            if not fund.get("_ok"):
                st.caption("Scarica i fondamentali (pulsante in alto) per l'analisi completa.")

        # ---- weekly candlestick chart ----
        st.markdown("**Grafico settimanale (MA 50 / 200 settimane)**")
        yrs = st.select_slider("Storico (anni)", options=[2, 3, 5, 10], value=5,
                               key="hist_years")
        try:
            bars = external.fetch_weekly(tkr)
        except Exception as e:  # noqa: BLE001
            bars = []
            st.warning(f"Grafico non disponibile: {e}")
        if bars:
            w = pd.DataFrame(bars).tail(yrs * 52)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=w["date"], open=w["open"], high=w["high"], low=w["low"],
                close=w["close"], name=tkr,
                increasing_line_color="#2dd4a7", decreasing_line_color="#ef5350"))
            if "sma200" in w:
                fig.add_trace(go.Scatter(x=w["date"], y=w["sma200"], name="MA 200w",
                                         line=dict(color="#f0a202", width=1.8)))
            if "sma50" in w:
                fig.add_trace(go.Scatter(x=w["date"], y=w["sma50"], name="MA 50w",
                                         line=dict(color="#58a6ff", width=1.2)))
            fig.update_layout(xaxis_rangeslider_visible=False,
                              legend=dict(orientation="h", y=1.02))
            st.plotly_chart(plotly_dark(fig, 460), use_container_width=True)
        tv = row.get("tv_symbol")
        if isinstance(tv, str) and tv:
            st.link_button(
                "📈 Apri il grafico su TradingView",
                f"https://www.tradingview.com/chart/?symbol={tv.replace(':', '%3A')}")

        # ---- full rule checklist ----
        with st.expander(f"Dettaglio regole del documento "
                         f"({res['passed']}/{res['applicable']} superate)", expanded=True):
            rule_df = pd.DataFrame([
                {"Regola": r["label"], "Valore": r["value"], "Soglia": r["rule"],
                 "Esito": "✅" if r["ok"] is True else ("❌" if r["ok"] is False else "—")}
                for r in res["rules"]])
            st.dataframe(rule_df, hide_index=True, use_container_width=True)

        with st.expander("Tutti i campi (scanner + yfinance)"):
            st.json({k: pv(v) for k, v in merged.items()
                     if not k.startswith("_") and k != "market_cap_b"})


# ---- selezione: un clic sulla riga apre il dettaglio (con selettore di fallback) ----
st.divider()
opts_df = f.sort_values("munger_score", ascending=False)
opt_list = opts_df.apply(lambda r: f"{r['ticker']} — {r['name']}", axis=1).tolist()
opt_by_ticker = dict(zip(opts_df["ticker"], opt_list))

sel_rows = event.selection["rows"] if event and getattr(event, "selection", None) else []
clicked = show.iloc[sel_rows[0]]["ticker"] if sel_rows else None
st.session_state.setdefault("last_clicked", None)
if clicked is not None and clicked != st.session_state.last_clicked:
    st.session_state.last_clicked = clicked
    if clicked in opt_by_ticker:
        st.session_state.detail_pick = opt_by_ticker[clicked]

if not opt_list:
    st.info("Nessun titolo con i filtri attuali.")
else:
    if st.session_state.get("detail_pick") not in opt_list:
        st.session_state.detail_pick = opt_list[0]
    pick = st.selectbox("🔍 Dettaglio titolo — clicca una riga sopra oppure scegli qui",
                        opt_list, key="detail_pick")
    render_detail(pick.split(" — ")[0])

with st.expander("ℹ️ Come sono calcolati i punteggi"):
    st.markdown(
        "### 🎩 Munger Score (0–100) — *relativo all'universo dello scanner*\n"
        "`munger_score = 65% · Qualità + 35% · Value`  (logica in `tools/enrich.py`)\n\n"
        "**Qualità (65%)** = media pesata di **percentili** calcolati sui 359 titoli "
        "(0 = peggiore della lista, 100 = migliore):\n"
        "- Quality grade 30% (A+ →100, A →93, A- →87, B+ →80 … F →10)\n"
        "- ROE 25% (percentile) · Profit margin 20% (percentile)\n"
        "- FA rating 15% (percentile) · Revenue growth 10% (percentile)\n\n"
        "**Value (35%)** = vicinanza alla **media a 200 settimane**. Curva a campana "
        "con picco (100) a circa **−2%** dalla MA200w (appena sotto = massimo "
        "'value'), che scende man mano che il prezzo si allontana (σ ≈ 12 punti %). "
        "Un titolo molto sopra la sua MA200w prende un Value basso.\n\n"
        "👉 È un punteggio **comparativo**: misura qualità + zona-valore *rispetto "
        "agli altri titoli della lista Munger*.\n\n"
        "---\n"
        "### 📄 Doc score (0–100%) — *assoluto, regole del tuo documento*\n"
        "`doc_score = regole superate ÷ regole applicabili × 100`  "
        "(logica in `tools/doc_analysis.py`)\n\n"
        "Confronta i dati del titolo con le soglie fisse del tuo "
        "*FUNDAMENTAL ANALYSIS.docx*:\n\n"
        "| Regola | Superata se | Fonte |\n"
        "|---|---|---|\n"
        "| P/E | ≤ 20 | yfinance |\n"
        "| ROE | ≥ 15% | scanner |\n"
        "| Debt/Equity | < 1 | yfinance |\n"
        "| Current ratio | ≥ 2 | yfinance |\n"
        "| Revenue growth | > 0 | scanner |\n"
        "| EPS growth | > 0 | yfinance |\n"
        "| Dividend payout | < 60% (se paga dividendo) | yfinance |\n"
        "| P/B | < 1 | yfinance |\n"
        "| Free cash flow | > 0 | yfinance |\n\n"
        "*Applicabili* = solo le regole per cui esiste il dato. Senza i fondamentali "
        "yfinance scaricati restano valutate solo **ROE** e **Revenue growth** (dallo "
        "scanner), quindi il punteggio è parziale finché non scarichi i fondamentali. "
        "I dati mancanti contano come «—» (non applicabile), mai come regola fallita.\n\n"
        "Le regole 10–12 del documento (growth vs value, diversificazione ≤5%/titolo, "
        "confronto di settore) sono giudizi di contesto e **non** sono punteggiate.")
