"""
Craigslist position tracker — MVP fragment.

Что делает:
  1. Читает config.yaml со списком поисковых запросов и наших объявлений.
  2. Через Playwright (Chromium, headless) с опциональным US-прокси заходит
     на Craigslist в нужный город, открывает search-URL, проходит N страниц.
  3. Для каждого объявления из tracked_listings ищет совпадение по id или title,
     фиксирует позицию в выдаче (absolute index + page).
  4. Пишет результат в output/positions_<run_date>.csv.

Запуск:
  python -m src.tracker --config src/config.yaml

ENV (опционально):
  PROXY_SERVER=http://us-residential-proxy.example:8000
  PROXY_USER=...
  PROXY_PASS=...
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

try:
    from playwright.async_api import async_playwright, BrowserContext, Page
except ImportError:
    print(
        "[!] Playwright не установлен. Запусти:\n"
        "    pip install playwright && playwright install chromium",
        file=sys.stderr,
    )
    raise


CRAIGSLIST_SEARCH = "https://{city}.craigslist.org/search/{section}?query={q}#search=1~gallery~{page}"
ID_RE = re.compile(r"/(\d{8,})\.html")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tracker")


@dataclass
class TrackedListing:
    id: str
    title_contains: str


@dataclass
class Query:
    city: str
    section: str
    keyword: str
    tracked_listings: list[TrackedListing]


@dataclass
class PositionRow:
    run_date: str
    city: str
    keyword: str
    listing_id: str
    listing_title: str
    position: int | None         # абсолютный индекс в выдаче (1-based); None = не найдено
    page: int | None
    url: str
    total_seen: int              # сколько всего результатов мы просмотрели за прогон


def load_config(path: Path) -> tuple[dict, list[Query]]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    queries = [
        Query(
            city=q["city"],
            section=q["section"],
            keyword=q["keyword"],
            tracked_listings=[TrackedListing(**t) for t in q["tracked_listings"]],
        )
        for q in raw["queries"]
    ]
    return raw["run"], queries


async def collect_results_on_page(page: Page) -> list[dict]:
    """Достать список объявлений с текущей страницы выдачи."""
    # Craigslist рендерит результаты как <li class="cl-static-search-result"> или
    # <li class="cl-search-result cl-search-view-mode-gallery"> в зависимости от вьюхи.
    # Берём оба варианта.
    items = await page.evaluate(
        """
        () => {
          const sel = 'li.cl-static-search-result, li.cl-search-result';
          const nodes = Array.from(document.querySelectorAll(sel));
          return nodes.map(n => {
            const a = n.querySelector('a');
            const title = (n.querySelector('.title, .label') || a || {}).textContent || '';
            const href = a ? a.href : '';
            return { title: title.trim(), href };
          }).filter(x => x.href);
        }
        """
    )
    return items


def extract_id(href: str) -> str | None:
    m = ID_RE.search(href or "")
    return m.group(1) if m else None


def match_listing(item: dict, tracked: TrackedListing) -> bool:
    item_id = extract_id(item.get("href", ""))
    if item_id and item_id == tracked.id:
        return True
    title = (item.get("title") or "").lower()
    return tracked.title_contains.lower() in title


async def scrape_query(context: BrowserContext, q: Query, run_cfg: dict, run_date: str) -> list[PositionRow]:
    rows: list[PositionRow] = []
    page = await context.new_page()
    found: dict[str, PositionRow] = {}
    position = 0

    try:
        for page_idx in range(run_cfg["max_pages"]):
            url = CRAIGSLIST_SEARCH.format(
                city=q.city,
                section=q.section,
                q=q.keyword.replace(" ", "+"),
                page=page_idx,
            )
            log.info("→ %s | %s | page %d", q.city, q.keyword, page_idx + 1)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Ждём пока подгрузятся карточки
            try:
                await page.wait_for_selector(
                    "li.cl-static-search-result, li.cl-search-result",
                    timeout=10_000,
                )
            except Exception:
                log.warning("  ! на странице нет карточек выдачи — возможно блок или капча")
                break

            items = await collect_results_on_page(page)
            if not items:
                break

            for item in items:
                position += 1
                for tracked in q.tracked_listings:
                    if tracked.id in found:
                        continue
                    if match_listing(item, tracked):
                        found[tracked.id] = PositionRow(
                            run_date=run_date,
                            city=q.city,
                            keyword=q.keyword,
                            listing_id=tracked.id,
                            listing_title=item["title"][:120],
                            position=position,
                            page=page_idx + 1,
                            url=item["href"],
                            total_seen=position,
                        )
                        log.info("  ✓ нашли %s на позиции #%d (стр. %d)",
                                 tracked.id, position, page_idx + 1)

            if all(t.id in found for t in q.tracked_listings):
                break

            lo, hi = run_cfg["page_delay_sec"]
            await asyncio.sleep(random.uniform(lo, hi))

        # Те, кого не нашли — пишем как not found
        for tracked in q.tracked_listings:
            if tracked.id in found:
                rows.append(found[tracked.id])
            else:
                rows.append(PositionRow(
                    run_date=run_date,
                    city=q.city,
                    keyword=q.keyword,
                    listing_id=tracked.id,
                    listing_title=tracked.title_contains,
                    position=None,
                    page=None,
                    url="",
                    total_seen=position,
                ))
                log.info("  ✗ %s не найден за %d просмотренных результатов",
                         tracked.id, position)
    finally:
        await page.close()
    return rows


def write_csv(rows: Iterable[PositionRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "run_date", "city", "keyword", "listing_id",
            "listing_title", "position", "page", "url", "total_seen",
        ])
        for r in rows:
            w.writerow([
                r.run_date, r.city, r.keyword, r.listing_id,
                r.listing_title,
                "" if r.position is None else r.position,
                "" if r.page is None else r.page,
                r.url, r.total_seen,
            ])
    log.info("Записан CSV: %s", out_path)


async def main_async(config_path: Path, out_dir: Path) -> int:
    run_cfg, queries = load_config(config_path)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    proxy_arg = None
    if run_cfg.get("use_proxy") and os.getenv("PROXY_SERVER"):
        proxy_arg = {
            "server": os.environ["PROXY_SERVER"],
            "username": os.getenv("PROXY_USER", ""),
            "password": os.getenv("PROXY_PASS", ""),
        }
        log.info("Используем прокси %s", proxy_arg["server"])

    all_rows: list[PositionRow] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=run_cfg.get("headless", True),
            proxy=proxy_arg,
        )
        context = await browser.new_context(
            user_agent=run_cfg["user_agent"],
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        try:
            for q in queries:
                rows = await scrape_query(context, q, run_cfg, run_date)
                all_rows.extend(rows)
        finally:
            await context.close()
            await browser.close()

    out_path = out_dir / f"positions_{run_date}.csv"
    write_csv(all_rows, out_path)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("src/config.yaml"))
    ap.add_argument("--out-dir", type=Path, default=Path("output"))
    args = ap.parse_args()
    return asyncio.run(main_async(args.config, args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
