"""doc_analysis.py — Evaluate stocks against the FUNDAMENTAL ANALYSIS.docx rules.

Encodes the "rules of thumb" from the user's fundamental-analysis document so
each stock can be scored against them. Pure logic (no I/O) so it is easy to test
and reuse from the dashboard.

Inputs are a merged dict combining:
  - scanner fields (roe, revenue_growth, ...)  [percent units, e.g. roe=33.1]
  - yfinance fundamentals (trailingPE, priceToBook, debtToEquity, currentRatio,
    payoutRatio, freeCashflow, earningsGrowth, ...) in their native yfinance units.

yfinance unit notes handled here:
  - debtToEquity is a PERCENT (30.27 => ratio 0.30) -> compared as /100.
  - returnOnEquity, revenueGrowth, earningsGrowth, payoutRatio are FRACTIONS
    (0.34 => 34%). The scanner's roe/revenue_growth are already percents.
"""

# Each rule: key, label, the document's rule-of-thumb, and an evaluator.
# evaluator(v) -> (ok: bool|None, value_for_display). None ok = not applicable.


def _num(x):
    try:
        if x is None or x == "":
            return None
        v = float(x)
        if v != v:  # NaN (e.g. pandas/numpy missing value)
            return None
        return v
    except (TypeError, ValueError):
        return None


def evaluate(m: dict) -> dict:
    """Evaluate one merged stock dict against the document rules.

    Returns {"rules": [...], "passed": int, "applicable": int, "doc_score": float}.
    """
    pe = _num(m.get("trailingPE"))
    pb = _num(m.get("priceToBook"))
    de = _num(m.get("debtToEquity"))            # percent
    cr = _num(m.get("currentRatio"))
    payout = _num(m.get("payoutRatio"))         # fraction
    fcf = _num(m.get("freeCashflow"))
    eps_g = _num(m.get("earningsGrowth"))       # fraction
    # ROE / revenue growth: prefer scanner (percent), fall back to yfinance (fraction)
    roe = _num(m.get("roe"))
    if roe is None and _num(m.get("returnOnEquity")) is not None:
        roe = _num(m.get("returnOnEquity")) * 100
    rev_g = _num(m.get("revenue_growth"))
    if rev_g is None and _num(m.get("revenueGrowth")) is not None:
        rev_g = _num(m.get("revenueGrowth")) * 100

    rules = []

    def add(key, label, thumb, ok, value):
        rules.append({"key": key, "label": label, "rule": thumb,
                      "ok": ok, "value": value})

    # 1. P/E 15-20 reasonable; low = undervalued. Pass = positive and <= 20.
    add("pe", "P/E Ratio", "15-20 ragionevole; basso = sottovalutato",
        (0 < pe <= 20) if pe is not None else None,
        None if pe is None else round(pe, 1))

    # 6. ROE >= 15%
    add("roe", "ROE", ">= 15%",
        (roe >= 15) if roe is not None else None,
        None if roe is None else round(roe, 1))

    # 2. Debt-to-Equity < 1
    add("de", "Debt/Equity", "< 1",
        (de / 100 < 1) if de is not None else None,
        None if de is None else round(de / 100, 2))

    # 3. Current Ratio >= 2
    add("current", "Current Ratio", ">= 2",
        (cr >= 2) if cr is not None else None,
        None if cr is None else round(cr, 2))

    # 4. Revenue growth positive (proxy for consistent growth)
    add("rev", "Revenue Growth", "positiva / consistente",
        (rev_g > 0) if rev_g is not None else None,
        None if rev_g is None else round(rev_g, 1))

    # 5. EPS growth positive
    add("eps", "EPS Growth", "in crescita",
        (eps_g > 0) if eps_g is not None else None,
        None if eps_g is None else round(eps_g * 100, 1))

    # 7. Dividend payout < 60% (only if it pays a dividend)
    if payout is None or payout == 0:
        add("payout", "Dividend Payout", "< 60% (se paga dividendi)", None,
            None if payout is None else round(payout * 100, 1))
    else:
        add("payout", "Dividend Payout", "< 60%",
            payout < 0.60, round(payout * 100, 1))

    # 8. P/B < 1 = undervalued (strict value lens)
    add("pb", "P/B Ratio", "< 1 = sottovalutato",
        (pb < 1) if pb is not None else None,
        None if pb is None else round(pb, 2))

    # 9. Free Cash Flow positive
    add("fcf", "Free Cash Flow", "positivo",
        (fcf > 0) if fcf is not None else None,
        None if fcf is None else round(fcf / 1e9, 2))  # $B

    applicable = sum(1 for r in rules if r["ok"] is not None)
    passed = sum(1 for r in rules if r["ok"] is True)
    score = round(100.0 * passed / applicable, 1) if applicable else None
    return {"rules": rules, "passed": passed, "applicable": applicable,
            "doc_score": score}


RULE_KEYS = ["pe", "roe", "de", "current", "rev", "eps", "payout", "pb", "fcf"]


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def snowflake_axes(m: dict) -> dict:
    """SimplyWall.st-style 5-axis scores (0-100, higher = better).

    Axes: Value, Future (growth), Past (performance), Health, Dividend.
    Each axis averages whatever sub-metrics are available; missing -> None.
    """
    pe = _num(m.get("trailingPE"))
    pb = _num(m.get("priceToBook"))
    de = _num(m.get("debtToEquity"))            # percent
    cr = _num(m.get("currentRatio"))
    payout = _num(m.get("payoutRatio"))         # fraction
    eps_g = _num(m.get("earningsGrowth"))       # fraction
    dy = _num(m.get("dividendYield"))           # percent (e.g. 0.93 = 0.93%)
    val_ma = _num(m.get("value_score"))         # from enrich.py (MA proximity)
    roe = _num(m.get("roe"))
    if roe is None and _num(m.get("returnOnEquity")) is not None:
        roe = _num(m.get("returnOnEquity")) * 100
    rev_g = _num(m.get("revenue_growth"))
    if rev_g is None and _num(m.get("revenueGrowth")) is not None:
        rev_g = _num(m.get("revenueGrowth")) * 100
    pm = _num(m.get("profit_margin"))

    # Value: cheaper = higher
    pe_s = _clamp(100 - (pe - 10) * 5) if pe is not None and pe > 0 else None
    pb_s = _clamp(100 - (pb - 1) * 25) if pb is not None and pb > 0 else None
    value = _mean([pe_s, pb_s, val_ma])

    # Future: growth
    future = _mean([
        _clamp(rev_g * 5) if rev_g is not None else None,
        _clamp(eps_g * 100 * 5) if eps_g is not None else None,
    ])

    # Past: quality / profitability
    past = _mean([
        _clamp(roe * (100 / 30)) if roe is not None else None,
        _clamp(pm * (100 / 30)) if pm is not None else None,
    ])

    # Health: balance sheet (None if no fundamentals)
    health = _mean([
        _clamp(100 - (de / 100) * 50) if de is not None else None,
        _clamp((cr - 1) * 100) if cr is not None else None,
    ])

    # Dividend: yield + payout sustainability
    if dy is None and payout is None:
        dividend = None
    elif (dy or 0) <= 0:
        dividend = 0.0
    else:
        dividend = _mean([
            _clamp(dy * 25) if dy is not None else None,
            _clamp(100 - payout * 100) if payout is not None else None,
        ])

    return {"Value": value, "Future": future, "Past": past,
            "Health": health, "Dividend": dividend}


RULE_REWARD_LABEL = {
    "pe": "Valutazione P/E ragionevole (≤20)",
    "roe": "ROE elevato (≥15%)",
    "de": "Debito contenuto (D/E <1)",
    "current": "Buona liquidità (current ratio ≥2)",
    "rev": "Ricavi in crescita",
    "eps": "Utili per azione in crescita",
    "payout": "Dividendo sostenibile (payout <60%)",
    "pb": "Prezzo sotto il valore di libro (P/B <1)",
    "fcf": "Free cash flow positivo",
}
RULE_RISK_LABEL = {
    "pe": "P/E elevato (>20)",
    "roe": "ROE sotto il 15%",
    "de": "Debito elevato (D/E ≥1)",
    "current": "Liquidità bassa (current ratio <2)",
    "rev": "Ricavi non in crescita",
    "eps": "Utili per azione non in crescita",
    "payout": "Payout dividendo elevato (≥60%)",
    "pb": "Prezzo sopra il valore di libro (P/B ≥1)",
    "fcf": "Free cash flow negativo",
}


if __name__ == "__main__":
    # quick self-test with MSFT-like values
    demo = {"roe": 33.1, "revenue_growth": 18.3, "trailingPE": 23.7,
            "priceToBook": 7.15, "debtToEquity": 30.27, "currentRatio": 1.28,
            "payoutRatio": 0.207, "freeCashflow": 37e9, "earningsGrowth": 0.234}
    res = evaluate(demo)
    for r in res["rules"]:
        print(f"{r['label']:16} {str(r['value']):>8}  {r['rule']:30} -> {r['ok']}")
    print(f"\ndoc_score = {res['doc_score']}  ({res['passed']}/{res['applicable']})")
