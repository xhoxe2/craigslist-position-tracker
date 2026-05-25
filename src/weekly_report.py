"""
Сводит дневные CSV (output/positions_YYYY-MM-DD.csv) в недельный отчёт.

Запуск:
  python -m src.weekly_report --in-dir output --out output/weekly.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


def load_rows(in_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(in_dir.glob("positions_*.csv")):
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    # ключ = (city, keyword, listing_id)
    bucket: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        bucket[(r["city"], r["keyword"], r["listing_id"])].append(r)

    out: list[dict] = []
    for (city, kw, lid), items in bucket.items():
        positions = [int(x["position"]) for x in items if x["position"]]
        days_visible = len(positions)
        days_missing = sum(1 for x in items if not x["position"])
        first = items[0]
        last = items[-1]
        delta = None
        if first["position"] and last["position"]:
            delta = int(last["position"]) - int(first["position"])
        out.append({
            "city": city,
            "keyword": kw,
            "listing_id": lid,
            "listing_title": last["listing_title"],
            "runs": len(items),
            "days_visible": days_visible,
            "days_missing": days_missing,
            "avg_position": round(mean(positions), 1) if positions else "",
            "best_position": min(positions) if positions else "",
            "worst_position": max(positions) if positions else "",
            "first_position": first["position"] or "",
            "last_position": last["position"] or "",
            "delta_first_to_last": "" if delta is None else delta,
        })
    return out


def write_summary(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        out_path.write_text("(нет данных)\n", encoding="utf-8")
        return
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", type=Path, default=Path("output"))
    ap.add_argument("--out", type=Path, default=Path("output/weekly_report.csv"))
    args = ap.parse_args()
    rows = load_rows(args.in_dir)
    summary = aggregate(rows)
    write_summary(summary, args.out)
    print(f"OK: {len(rows)} строк агрегировано в {len(summary)} линий → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
