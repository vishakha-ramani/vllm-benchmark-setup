#!/usr/bin/env python3
"""Convert guidellm benchmark CSV output to JSON.

guidellm emits CSVs with two- or three-row headers (category / sub /
optional stat). This script collapses them into ``cat | sub | stat``
column names and coerces numeric values.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _coerce(value: str) -> Any:
    try:
        return int(value) if "." not in value else float(value)
    except (ValueError, AttributeError):
        return value


def csv_to_json(csv_path: Path) -> List[Dict[str, Any]]:
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        first, second, third = next(reader), next(reader), next(reader)

        stat_markers = {"Mean", "Median", "Std Dev", "Percentiles"}
        three_header_rows = any(v in stat_markers for v in third)

        if three_header_rows:
            headers = [
                " | ".join(p.strip() for p in (a, b, c) if p.strip())
                for a, b, c in zip(first, second, third)
            ]
            data_rows = list(reader)
        else:
            headers = [
                " | ".join(p.strip() for p in (a, b) if p.strip())
                for a, b in zip(first, second)
            ]
            data_rows = [third] + list(reader)

        records: List[Dict[str, Any]] = []
        for row in data_rows:
            record = {key: _coerce(value) for key, value in zip(headers, row) if key}
            records.append(record)
        return records


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", type=Path, help="Input CSV file")
    p.add_argument("json", nargs="?", type=Path,
                   help="Output JSON file (default: <csv-stem>.json)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_path = args.json or args.csv.with_suffix(".json")

    try:
        data = csv_to_json(args.csv)
    except FileNotFoundError as e:
        sys.exit(f"CSV not found: {e}")

    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {len(data)} rows to {out_path}")


if __name__ == "__main__":
    main()
