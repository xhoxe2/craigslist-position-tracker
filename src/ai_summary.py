"""
AI-сумарі тижневого звіту: бере weekly_report.csv → передає в Gemini → отримує
human-readable звіт українською з 2-4 конкретними рекомендаціями для менеджера.

Це другий шар автоматизації поверх скрейпера. Сам по собі скрейпер видає
таблицю цифр, але менеджер хоче бачити "що з цим робити". Це і робить LLM.

Запуск:
  export GEMINI_API_KEY=...
  python -m src.ai_summary --in output/weekly_report.csv --out output/weekly_summary.txt

Якщо ключа немає — скрипт у --dry-run режимі покаже промпт, який буде
відправлено в LLM. Готовий sample-вивід лежить у output/weekly_summary.txt.
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


def call_gemini(system: str, user: str, model: str = "gemini-flash-latest") -> str:
    """Викликає Google Gemini API. Ключ читається з GEMINI_API_KEY.

    Примітка: Gemini 2.5+ моделі за замовчуванням мають "thinking" режим, який
    з'їдає вихідний токен-бюджет до того, як з'явиться текст. Тому ставимо
    достатньо великий ліміт або вимикаємо thinking явно.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print(
            "[!] google-genai не встановлений. Запусти:\n    pip install google-genai",
            file=sys.stderr,
        )
        raise

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=Path("output/weekly_report.csv"))
    ap.add_argument("--out", type=Path, default=Path("output/weekly_summary.txt"))
    ap.add_argument("--model", default="gemini-flash-latest",
                    help="Gemini model id (flash-latest = швидкий/дешевий, pro-latest = якісніший)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Не викликати API — тільки показати prompt")
    args = ap.parse_args()

    rows = load_rows(args.inp)
    user_prompt = build_user_prompt(rows)

    if args.dry_run or not os.getenv("GEMINI_API_KEY"):
        out = (
            "=== SYSTEM ===\n" + SYSTEM_PROMPT + "\n\n"
            "=== USER ===\n" + user_prompt + "\n\n"
            "[i] GEMINI_API_KEY не виставлено або --dry-run.\n"
            "    Це prompt, який буде відправлено в Gemini.\n"
            "    Готовий sample-вивід — у output/weekly_summary.txt"
        )
        print(out)
        return 0

    summary = call_gemini(SYSTEM_PROMPT, user_prompt, model=args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"\n--- Записано: {args.out} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
