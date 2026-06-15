"""fetch_scanner.py — Download AskLivermore stock-scanner results to local files.

The AskLivermore results endpoint is a public JSON API (no auth required):
    GET https://www.asklivermore.com/api/scanners/<scanner_id>/results
    -> {count, matches: [...], sort_by, sort_dir, scanner_id}

Each match is a stock with ~32 fields (fundamentals + technicals + market data).
This tool fetches one scanner and writes both raw JSON and a flat CSV to .tmp/.

Usage:
    python tools/fetch_scanner.py                 # defaults to munger-200w
    python tools/fetch_scanner.py munger-200w
    python tools/fetch_scanner.py <scanner_id> --out .tmp

Server-side sort params are ignored by the API, so sort/filter downstream.
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("ASKLIVERMORE_BASE_URL", "https://www.asklivermore.com")
DEFAULT_SCANNER = "munger-200w"

# A browser-like header set; the endpoint is public but some hosts gate on these.
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": BASE_URL + "/",
    "Origin": BASE_URL,
}


def fetch_scanner(scanner_id: str, timeout: int = 30) -> dict:
    """Fetch one scanner's results. Returns the parsed JSON payload."""
    url = f"{BASE_URL}/api/scanners/{scanner_id}/results"
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "matches" not in data:
        raise ValueError(f"Unexpected response shape, keys={list(data)}")
    return data


def save_json(data: dict, out_dir: str, scanner_id: str) -> str:
    path = os.path.join(out_dir, f"{scanner_id}_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def save_csv(matches: list, out_dir: str, scanner_id: str) -> str:
    path = os.path.join(out_dir, f"{scanner_id}_results.csv")
    # Union of all keys preserves any field that appears in some rows only.
    fields: list = []
    for m in matches:
        for k in m:
            if k not in fields:
                fields.append(k)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(matches)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch an AskLivermore scanner.")
    parser.add_argument("scanner_id", nargs="?", default=DEFAULT_SCANNER,
                        help=f"Scanner id (default: {DEFAULT_SCANNER})")
    parser.add_argument("--out", default=".tmp", help="Output directory (default: .tmp)")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    try:
        data = fetch_scanner(args.scanner_id)
    except requests.HTTPError as e:
        print(f"[error] HTTP {e.response.status_code} fetching '{args.scanner_id}': {e}",
              file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — surface any failure clearly
        print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    matches = data["matches"]
    data["_fetched_at"] = datetime.now(timezone.utc).isoformat()

    json_path = save_json(data, args.out, args.scanner_id)
    csv_path = save_csv(matches, args.out, args.scanner_id)

    print(f"[ok] scanner={args.scanner_id} count={data.get('count')} "
          f"matches={len(matches)}")
    print(f"[ok] json -> {json_path}")
    print(f"[ok] csv  -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
