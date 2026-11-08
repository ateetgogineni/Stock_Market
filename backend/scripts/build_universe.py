"""Build the instrument universe from NSE's official securities master.

Usage:
    python scripts/build_universe.py                       # download EQUITY_L.csv from NSE
    python scripts/build_universe.py path/to/EQUITY_L.csv  # use a local copy

EQUITY_L.csv is published by NSE at
https://archives.nseindia.com/content/equities/EQUITY_L.csv and lists every
main-board NSE equity with its ISIN. We use it only as a reference securities
master (identifiers), never as a price source.

Two outputs:
* app/universe/nse_universe.json: the curated CORE universe (plan section 2.1).
  These large caps have been checked end to end against the dev data provider.
* app/universe/nse_master.json: every other NSE main-board equity, served as
  EXTENDED coverage. Identifiers are verified; provider data is not
  pre-validated, so the data-quality gates decide what each report can say.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

SOURCE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
SERIES = {"EQ", "BE", "BZ"}

SUPPORTED_NSE_SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "ITC", "SBIN",
    "BHARTIARTL", "HINDUNILVR", "LT", "AXISBANK", "ASIANPAINT", "MARUTI",
    "SUNPHARMA", "WIPRO", "HCLTECH", "TATASTEEL", "KOTAKBANK", "BAJFINANCE",
    "NTPC", "TITAN", "ULTRACEMCO", "POWERGRID", "NESTLEIND",
]

UNIVERSE_DIR = Path(__file__).resolve().parent.parent / "app" / "universe"
CORE_OUT = UNIVERSE_DIR / "nse_universe.json"
MASTER_OUT = UNIVERSE_DIR / "nse_master.json"


def read_master(csv_path: str | None) -> tuple[list[dict], str]:
    if csv_path:
        text = Path(csv_path).read_text(encoding="utf-8")
    else:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(reader)]
    rows = [dict(zip(header, (c.strip() for c in raw))) for raw in reader if raw]
    return rows, date.today().isoformat()


def listing_date(row: dict) -> str | None:
    try:
        return datetime.strptime(row["DATE OF LISTING"], "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def main(csv_path: str | None) -> None:
    rows, file_date = read_master(csv_path)
    by_symbol = {r["SYMBOL"]: r for r in rows}

    core, missing = [], []
    for symbol in SUPPORTED_NSE_SYMBOLS:
        row = by_symbol.get(symbol)
        if row is None or row.get("SERIES") != "EQ":
            missing.append(symbol)
            continue
        isin = row["ISIN NUMBER"]
        core.append(
            {
                "instrument_id": f"IN:{isin}",
                "isin": isin,
                "name": row["NAME OF COMPANY"],
                "security_type": "equity",
                "country": "IN",
                "currency": "INR",
                "nse_listing_date": listing_date(row),
                "face_value": row["FACE VALUE"],
                "listings": [
                    {
                        "exchange": "NSE",
                        "symbol": symbol,
                        "series": "EQ",
                        "provider_symbol": f"{symbol}.NS",
                        "is_primary": True,
                        "identifier_verified": True,
                        "verification_source": "NSE EQUITY_L.csv",
                    },
                    {
                        "exchange": "BSE",
                        "symbol": symbol,
                        "scrip_code": None,
                        "provider_symbol": f"{symbol}.BO",
                        "is_primary": False,
                        "identifier_verified": False,
                        "verification_source": "Not verified: BSE scrip master not loaded. "
                        "Listing inferred from the dev provider symbol.",
                    },
                ],
            }
        )

    core_isins = {i["isin"] for i in core}
    seen: set[str] = set()
    master = []
    for r in rows:
        isin, series = r.get("ISIN NUMBER", ""), r.get("SERIES", "")
        if series not in SERIES or not isin or isin in core_isins or isin in seen:
            continue
        seen.add(isin)
        # Compact rows: [symbol, name, series, isin, listing date, face value]
        master.append([r["SYMBOL"], r["NAME OF COMPANY"], series, isin, listing_date(r), r.get("FACE VALUE")])
    master.sort(key=lambda m: m[0])

    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    CORE_OUT.write_text(json.dumps({
        "universe_id": "nse-core-dev-v1",
        "description": "Curated core universe of large NSE-listed cash equities.",
        "source": SOURCE_URL,
        "source_file_date": file_date,
        "instruments": core,
    }, indent=2) + "\n", encoding="utf-8")
    MASTER_OUT.write_text(json.dumps({
        "universe_id": "nse-master-dev-v1",
        "description": "All other NSE main-board equities (series EQ, BE, BZ), served as extended coverage.",
        "source": SOURCE_URL,
        "source_file_date": file_date,
        "columns": ["symbol", "name", "series", "isin", "listing_date", "face_value"],
        "rows": master,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"core: {len(core)} instruments -> {CORE_OUT.name}")
    print(f"extended: {len(master)} instruments -> {MASTER_OUT.name}")
    if missing:
        print("core symbols not found in master (skipped):", ", ".join(missing))


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__)
    main(sys.argv[1] if len(sys.argv) == 2 else None)
