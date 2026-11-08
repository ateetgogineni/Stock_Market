"""Build the options contract master from NSE's daily F&O contract file.

Usage:
    python scripts/build_fo_master.py                                  # download the latest file from NSE
    python scripts/build_fo_master.py path/to/NSE_FO_contract_DDMMYYYY.csv.gz

NSE replaced fo_mktlots.csv with this "MII contract file" in April 2024
(circular NSE/FAOP/61157). It lists every live derivatives contract: underlying,
expiry, strike, option type, lot size, settlement method and exercise style.
We keep only identifiers and contract specifications, never prices.

Conventions in the file (checked against known contracts):
* XpryDt is seconds since 1980-01-01; only the date part is used.
* StrkPric is in paise (divide by 100).
* DelFlg = "Y" marks deleted contracts, which are skipped.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

URL = "https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_{d}.csv.gz"
NSE_EPOCH = datetime(1980, 1, 1, tzinfo=timezone.utc)
OUT = Path(__file__).resolve().parent.parent / "app" / "universe" / "nse_fo_contracts.json"


def fetch(path: str | None) -> tuple[bytes, str]:
    if path:
        name = Path(path).name
        return Path(path).read_bytes(), name
    for back in range(0, 10):
        d = (date.today() - timedelta(days=back)).strftime("%d%m%Y")
        req = urllib.request.Request(URL.format(d=d), headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if data[:2] == b"\x1f\x8b":
                return data, f"NSE_FO_contract_{d}.csv.gz"
        except Exception:
            continue
    sys.exit("Could not download an NSE F&O contract file for the last 10 days.")


def main(path: str | None) -> None:
    raw, name = fetch(path)
    file_date = datetime.strptime(name.split("_")[-1].split(".")[0], "%d%m%Y").date().isoformat()
    rows = csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8")))

    sides: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))  # sym -> expiry -> strike -> {CE, PE}
    lots: dict = defaultdict(lambda: defaultdict(set))
    meta: dict = {}
    for r in rows:
        kind = r.get("FinInstrmNm")
        if kind not in ("OPTIDX", "OPTSTK") or r.get("DelFlg") == "Y":
            continue
        sym = r["TckrSymb"].strip()
        expiry = (NSE_EPOCH + timedelta(seconds=int(r["XpryDt"]))).date().isoformat()
        strike = int(r["StrkPric"]) / 100
        sides[sym][expiry][strike].add(r["OptnTp"])
        lots[sym][expiry].add(int(r["MinLot"]))
        meta[sym] = {
            "type": "index" if kind == "OPTIDX" else "stock",
            "settlement": {"C": "cash", "P": "physical"}.get(r["SttlmMtd"], r["SttlmMtd"]),
            "exercise": {"E": "european", "A": "american"}.get(r["OptnExrcStyle"], r["OptnExrcStyle"]),
        }

    underlyings = {}
    for sym in sorted(sides):
        expiries = {}
        for expiry in sorted(sides[sym]):
            strikes = sorted(k for k, s in sides[sym][expiry].items() if s == {"CE", "PE"})
            one_sided = sum(1 for s in sides[sym][expiry].values() if s != {"CE", "PE"})
            lot_set = sorted(lots[sym][expiry])
            expiries[expiry] = {
                "lot_size": lot_set[0] if len(lot_set) == 1 else None,
                "lot_sizes": lot_set,
                "strikes": [int(k) if k == int(k) else k for k in strikes],
                "one_sided_strikes": one_sided,
            }
        underlyings[sym] = {**meta[sym], "expiries": expiries}

    OUT.write_text(json.dumps({
        "source": URL.format(d=name.split("_")[-1].split(".")[0]),
        "file_date": file_date,
        "description": "NSE equity-derivatives option contracts (identifiers and specifications only).",
        "underlyings": underlyings,
    }, separators=(",", ":")) + "\n", encoding="utf-8")
    n_idx = sum(1 for u in underlyings.values() if u["type"] == "index")
    print(f"{len(underlyings)} option underlyings ({n_idx} indices) from {name} -> {OUT.name} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__)
    main(sys.argv[1] if len(sys.argv) == 2 else None)
