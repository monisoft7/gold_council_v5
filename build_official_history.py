# -*- coding: utf-8 -*-
"""تنزيل واحد ثم عمل محلي متكرر؛ يحافظ على حدود APIs والرصيد."""
from __future__ import annotations

import argparse
from pathlib import Path

from official_macro_data import FRED_SERIES, BLS_SERIES, fred_initial_release, bls_series


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2026-08-30")
    parser.add_argument("--out-dir", default="data_cache/official")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    for name, series_id in FRED_SERIES.items():
        target = out / f"fred_{name}.csv"
        if target.exists() and not args.refresh:
            print(f"cached {target}")
            continue
        frame = fred_initial_release(series_id, args.start, args.end)
        frame.to_csv(target, index=False, encoding="utf-8")
        print(f"saved {name}: {len(frame)} rows")

    audit = out / "bls_live_audit.csv"
    if not audit.exists() or args.refresh:
        frame = bls_series(BLS_SERIES.values(), int(args.start[:4]), int(args.end[:4]))
        frame.to_csv(audit, index=False, encoding="utf-8")
        print(f"saved BLS audit: {len(frame)} rows")


if __name__ == "__main__":
    main()
