"""
AI-сумарі тижневого звіту: бере weekly_report.csv → передає в Claude → отримує
human-readable параграф українською з конкретними рекомендаціями для менеджера.

Це другий шар автоматизації поверх скрейпера. Сам по собі скрейпер видає таблицю
цифр, але менеджер хоче бачити "що з цим робити" — це і робить LLM.

Запуск:
  export ANTHROPIC_API_KEY=sk-ant-...
  python -m src.ai_summary --in output/weekly_report.csv --out output/weekly_summary.txt

Якщо ключа немає — скрипт виведе текст промпту, який буде відправлено в LLM
(для review). Готовий приклад виводу лежить у output/weekly_summary.txt.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from textwrap import dedent

SYSTEM_PROMPT = dedent("""\
    Ти — асистент менеджера, який стежить за позиціями наших оголошень на Craigslist.
    Тобі дають CSV-таблицю з тижневим звітом: для кожного оголошення вказано
    середню/найкращу/найгіршу позицію, скільки днів воно було видиме і скільки
    випадало з видачі, а також зміна позиції з першого дня тижня до останнього.

    Твоя задача — написати короткий звіт українською мовою для менеджера:
      1. Один абзац — загальна картина тижня (що добре, що погано).
      2. Список з 2-4 конкретних рекомендацій. Кожна рекомендація має посилатися
         на конкретні дані з таблиці (id оголошення, місто, цифру).
      3. Без води. Без слів "оптимізація", "синергія", "екосистема". Конкретно.
    Не вигадуй цифр, яких немає в таблиці. Якщо даних замало для висновку —
    скажи це прямо.
""").strip()


def build_user_prompt(rows: list[dict]) -> str:
    """Перетворити CSV-рядки на компактний markdown-блок для LLM."""
    lines = ["Тижневий звіт по позиціях наших оголошень:", ""]
    lines.append("| Місто | Запит | ID | Прогонів | Видиме | Випало | Avg | Best | Worst | Δ |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['city']} | {r['keyword']} | {r['listing_id']} | "
            f"{r['runs']} | {r['days_visible']} | {r['days_missing']} | "
            f"{r['avg_position']} | {r['best_position']} | {r['worst_position']} | "
            f"{r['delta_first_to_last']} |"
        )
    lines += [
        "",
        "Δ (delta_first_to_last) — позитивне число = позиція погіршилась.",
        "Видиме/Випало — кількість днів за тиждень, коли оголошення було/не було знайдене у топ-N.",
    ]
    return "\n".join(lines)


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def call_claude(system: str, user: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Викликає Anthropic API. Якщо anthropic не встановлений — підказує як поставити."""
    try:
        from anthropic import Anthropic
    except ImportError:
        print(
            "[!] anthropic не встановлений. Запусти:\n    pip install anthropic",
            file=sys.stderr,
        )
        raise

    client = Anthropic()  # читає ANTHROPIC_API_KEY з ENV
    msg = client.messages.create(
        model=model,
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in msg.content if hasattr(block, "text"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=Path("output/weekly_report.csv"))
    ap.add_argument("--out", type=Path, default=Path("output/weekly_summary.txt"))
    ap.add_argument("--model", default="claude-haiku-4-5-20251001",
                    help="Anthropic model id (haiku = дешевий, sonnet = якісніший)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Не викликати API — тільки показати prompt")
    args = ap.parse_args()

    rows = load_rows(args.inp)
    user_prompt = build_user_prompt(rows)

    if args.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
        out = (
            "=== SYSTEM ===\n" + SYSTEM_PROMPT + "\n\n"
            "=== USER ===\n" + user_prompt + "\n\n"
            "[i] ANTHROPIC_API_KEY не виставлено або --dry-run.\n"
            " Це prompt, який буде відправлено в Claude. Готовий sample-вивід — у output/weekly_summary.txt]"
        )
        print(out)
        return 0

    summary = call_claude(SYSTEM_PROMPT, user_prompt, model=args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"\n--- Записано: {args.out} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
