"""enrich.py — Add derived analytics to AskLivermore scanner data.

Reads a raw scanner JSON (from fetch_scanner.py) and adds a transparent,
percentile-based **Munger Score** plus helper columns, then writes enriched
JSON + CSV to .tmp/.

The Munger Score (0-100) blends two ideas from Charlie Munger's philosophy:
  - QUALITY  (65%): wonderful businesses — ROE, profit margin, revenue growth,
                    fundamental rating, and the site's letter quality grade.
  - VALUE    (35%): fair price — proximity to the 200-week moving average
                    "value zone" (peaks just at/below the MA, penalises far above).

All inputs are ranked as percentiles within the current universe, so the score
is relative to the scanner's own population and robust to outliers.

Usage:
    python tools/enrich.py                         # munger-200w from .tmp
    python tools/enrich.py <scanner_id> --in .tmp --out .tmp
"""
import argparse
import csv
import json
import math
import os
import sys

# Letter grade -> 0..100. Unknown grades map to 50 (neutral).
GRADE_MAP = {
    "A+": 100, "A": 93, "A-": 87,
    "B+": 80, "B": 73, "B-": 67,
    "C+": 60, "C": 53, "C-": 47,
    "D+": 40, "D": 33, "D-": 27,
    "F": 10,
}

# Quality sub-weights (sum to 1.0)
Q_WEIGHTS = {
    "grade": 0.30,
    "roe": 0.25,
    "profit_margin": 0.20,
    "fa_rating": 0.15,
    "revenue_growth": 0.10,
}
# Top-level blend
QUALITY_W = 0.65
VALUE_W = 0.35

# Value-zone curve: gaussian peak around the 200w MA.
VALUE_TARGET = -2.0   # %from200w where value is "best" (just below the MA)
VALUE_SIGMA = 12.0    # spread in percentage points


def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def percentile_ranks(values):
    """Return list of 0..100 percentile ranks aligned to `values`.

    None values get rank None. Ties share the average rank. Higher value ->
    higher rank.
    """
    idx = [(v, i) for i, v in enumerate(values) if v is not None]
    ranks = [None] * len(values)
    n = len(idx)
    if n == 0:
        return ranks
    if n == 1:
        ranks[idx[0][1]] = 50.0
        return ranks
    idx.sort(key=lambda t: t[0])
    # assign average ranks for ties
    j = 0
    while j < n:
        k = j
        while k + 1 < n and idx[k + 1][0] == idx[j][0]:
            k += 1
        avg_pos = (j + k) / 2.0  # 0-based average position
        pct = 100.0 * avg_pos / (n - 1)
        for p in range(j, k + 1):
            ranks[idx[p][1]] = round(pct, 2)
        j = k + 1
    return ranks


def value_score(pct_from_200w):
    if pct_from_200w is None:
        return None
    d = pct_from_200w - VALUE_TARGET
    return round(100.0 * math.exp(-(d * d) / (2 * VALUE_SIGMA * VALUE_SIGMA)), 2)


def enrich(matches):
    roe_r = percentile_ranks([_num(m.get("roe")) for m in matches])
    pm_r = percentile_ranks([_num(m.get("profit_margin")) for m in matches])
    rg_r = percentile_ranks([_num(m.get("revenue_growth")) for m in matches])
    fa_r = percentile_ranks([_num(m.get("fa_rating")) for m in matches])

    for i, m in enumerate(matches):
        grade = GRADE_MAP.get(str(m.get("quality", "")).strip(), 50.0)
        parts = {
            "grade": grade,
            "roe": roe_r[i],
            "profit_margin": pm_r[i],
            "fa_rating": fa_r[i],
            "revenue_growth": rg_r[i],
        }
        # weighted quality over the components that are available
        tot_w = sum(Q_WEIGHTS[k] for k, v in parts.items() if v is not None)
        if tot_w == 0:
            quality = None
        else:
            quality = sum(Q_WEIGHTS[k] * v for k, v in parts.items() if v is not None) / tot_w
        vscore = value_score(_num(m.get("pct_from_200w")))

        if quality is not None and vscore is not None:
            munger = QUALITY_W * quality + VALUE_W * vscore
        elif quality is not None:
            munger = quality
        else:
            munger = None

        m["quality_score"] = round(quality, 1) if quality is not None else None
        m["value_score"] = round(vscore, 1) if vscore is not None else None
        m["munger_score"] = round(munger, 1) if munger is not None else None

    # rank by munger_score desc (None last)
    ordered = sorted(
        range(len(matches)),
        key=lambda i: (matches[i]["munger_score"] is None,
                       -(matches[i]["munger_score"] or 0)),
    )
    for rank, i in enumerate(ordered, start=1):
        matches[i]["munger_rank"] = rank
    return matches


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich an AskLivermore scanner JSON.")
    ap.add_argument("scanner_id", nargs="?", default="munger-200w")
    ap.add_argument("--in", dest="in_dir", default=".tmp")
    ap.add_argument("--out", dest="out_dir", default=".tmp")
    args = ap.parse_args()

    src = os.path.join(args.in_dir, f"{args.scanner_id}_results.json")
    if not os.path.exists(src):
        print(f"[error] not found: {src} (run fetch_scanner.py first)", file=sys.stderr)
        return 1
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    matches = enrich(data["matches"])
    os.makedirs(args.out_dir, exist_ok=True)

    jpath = os.path.join(args.out_dir, f"{args.scanner_id}_enriched.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    fields = []
    for m in matches:
        for k in m:
            if k not in fields:
                fields.append(k)
    cpath = os.path.join(args.out_dir, f"{args.scanner_id}_enriched.csv")
    with open(cpath, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(matches)

    top = sorted(matches, key=lambda m: -(m["munger_score"] or 0))[:5]
    print(f"[ok] enriched {len(matches)} rows -> {cpath}")
    print("[ok] top 5 by munger_score: " +
          ", ".join(f"{m['ticker']}({m['munger_score']})" for m in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
