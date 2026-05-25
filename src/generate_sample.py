"""
Генерирует синтетические "позиции" — нужен для демо без US-IP/прокси.
Создаёт 7 файлов output/positions_<date>.csv за прошлую неделю,
чтобы потом weekly_report.py собрал из них сводку.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

LISTINGS = [
    # (city, keyword, listing_id, title, base_position)
    ("newyork", "iphone 15 pro", "7700000001", "iPhone 15 Pro 256GB Unlocked — Like New", 4),
    ("newyork", "iphone 15 pro", "7700000002", "iPhone 15 Pro Max 512GB Titanium Blue", 11),
    ("losangeles", "macbook pro m3", "7700000010", "MacBook Pro 14 M3 16GB 512GB Space Black", 7),
    ("chicago", "office chair herman miller", "7700000020", "Herman Miller Aeron Size B Fully Loaded", 2),
]

OUT = Path("output")
OUT.mkdir(exist_ok=True)

end = date.today()
start = end - timedelta(days=6)

for d in range((end - start).days + 1):
    day = start + timedelta(days=d)
    rows = []
    for city, kw, lid, title, base in LISTINGS:
        # Лёгкий drift + редкие "выпадения"
        drift = random.choice([-1, 0, 0, 1, 2])
        pos = max(1, base + drift + d // 3)
        # 1 из ~14 шансов вылететь из выдачи
        dropped = random.random() < 0.07
        rows.append({
            "run_date": day.isoformat(),
            "city": city,
            "keyword": kw,
            "listing_id": lid,
            "listing_title": title,
            "position": "" if dropped else pos,
            "page": "" if dropped else (1 if pos <= 120 else 2),
            "url": "" if dropped else f"https://{city}.craigslist.org/d/sample/{lid}.html",
            "total_seen": 360,
        })
    out_path = OUT / f"positions_{day.isoformat()}.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_path}")
