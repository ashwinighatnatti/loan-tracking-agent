"""Convert selected JSON files in each data folder to pipe-delimited .csv files.

Usage:
    python json_to_csv.py [data_dir]

data_dir defaults to ./data next to this script.
"""
import csv
import json
import sys
from pathlib import Path

# Requested names plus the variants actually used on disk.
TARGET_FILES = {
    "agent.json", "agents.json",
    "payee.json",
    "carrier.json", "carriers.json",
    "properties.json", "property.json",
}


def read_json(path: Path):
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return json.loads(text)


def to_rows(data):
    if isinstance(data, dict):
        data = [data]
    return [r if isinstance(r, dict) else {"value": r} for r in data]


def cell(value):
    # Lists of scalars become comma-separated; other nested values stay compact JSON.
    if isinstance(value, list) and not any(isinstance(v, (list, dict)) for v in value):
        return ",".join("" if v is None else str(v) for v in value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return "" if value is None else value


def convert(json_path: Path) -> Path:
    rows = to_rows(read_json(json_path))
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    csv_path = json_path.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="|")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: cell(v) for k, v in row.items()})
    return csv_path


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
    folders = sorted(p for p in data_dir.iterdir() if p.is_dir())

    for folder in folders:
        print(folder.name)
        for json_path in sorted(folder.glob("*.json")):
            if json_path.name.lower() not in TARGET_FILES:
                continue
            try:
                csv_path = convert(json_path)
                print(f"  {json_path.name} -> {csv_path.name}")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"  {json_path.name}: FAILED ({e})")


if __name__ == "__main__":
    main()
