import argparse
from pathlib import Path

from cftc_cot_data import fetch_range


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--out", default="data_cache/official/cftc_gold_cot.csv")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists() and not args.refresh:
        print(f"cached {target}")
        return
    data = fetch_range(args.start_year, args.end_year)
    target.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(target, index=False, encoding="utf-8")
    print(f"saved {len(data)} CFTC gold reports -> {target}")


if __name__ == "__main__":
    main()
