"""Local, dependency-free export helpers for BuildSales Insight."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


EXPORT_COLUMNS = (
    ("sold_at", "Дата"),
    ("material", "Матеріал"),
    ("category", "Категорія"),
    ("manager", "Менеджер"),
    ("customer", "Клієнт"),
    ("quantity", "Кількість"),
    ("unit_price", "Ціна за одиницю, ₴"),
    ("revenue", "Виручка, ₴"),
)

IMPORT_TEMPLATE_COLUMNS = (
    "sold_at",
    "material",
    "manager",
    "customer",
    "quantity",
    "unit_price",
)


def anonymize_sales_rows(rows: list[dict]) -> list[dict]:
    """Return copies with stable local aliases for customers and managers.

    Aliases preserve analytical relationships inside one exported file while
    preventing direct disclosure of the source names. The original rows and
    SQLite database are never changed.
    """
    managers = sorted({str(row.get("manager", "")) for row in rows})
    customers = sorted({str(row.get("customer", "")) for row in rows})
    manager_aliases = {
        value: f"Менеджер {index:03d}" for index, value in enumerate(managers, start=1)
    }
    customer_aliases = {
        value: f"Клієнт {index:03d}" for index, value in enumerate(customers, start=1)
    }
    return [
        {
            **row,
            "manager": manager_aliases[str(row.get("manager", ""))],
            "customer": customer_aliases[str(row.get("customer", ""))],
        }
        for row in rows
    ]


def create_sales_import_template(destination: str | Path) -> Path:
    """Create an empty UTF-8 CSV template accepted by the sales importer."""
    path = Path(destination)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        csv.writer(file).writerow(IMPORT_TEMPLATE_COLUMNS)
    return path


def _markdown_value(value: object) -> str:
    """Format a value safely for a one-cell Markdown table representation."""
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def export_analytics_report(
    summary: dict,
    materials: list[dict],
    active_filters: dict[str, str],
    destination: str | Path,
    created_at: datetime | None = None,
) -> Path:
    """Write a reproducible local Markdown report of the analytical results."""
    path = Path(destination)
    timestamp = (created_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    filter_lines = [
        f"- **{_markdown_value(label)}:** {_markdown_value(value or 'усі дані')}"
        for label, value in active_filters.items()
    ]
    lines = [
        "# Аналітичний звіт BuildSales Insight",
        "",
        f"Дата формування: {timestamp}",
        "",
        "## Параметри вибірки",
        *filter_lines,
        "",
        "## Ключові показники",
        "",
        f"- Виручка: **{float(summary.get('revenue', 0)):,.2f} ₴**",
        f"- Кількість угод: **{int(summary.get('deals', 0))}**",
        f"- Матеріалів у вибірці: **{int(summary.get('materials', 0))}**",
        f"- Високий ризик CPRI: **{int(summary.get('high_risk', 0))}**",
        "",
        "## Рекомендації за матеріалами",
        "",
        "| Матеріал | Прогноз +1 | CPRI | Закупити | Надійність | SADI | MAE |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for material in materials:
        forecast = material.get("forecast", [])
        next_demand = forecast[0]["quantity"] if forecast else "—"
        procurement = material.get("procurement", {})
        anomaly = material.get("anomaly", {})
        confidence = procurement.get("confidence")
        anomaly_score = anomaly.get("score")
        accuracy = material.get("accuracy", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_value(material.get("name")),
                    _markdown_value(next_demand),
                    _markdown_value(material.get("risk", {}).get("score")),
                    _markdown_value(procurement.get("order_quantity")),
                    _markdown_value(None if confidence is None else f"{confidence}%"),
                    _markdown_value(
                        None
                        if anomaly_score is None
                        else f"{anomaly_score:+.1f}% ({anomaly.get('direction')})"
                    ),
                    _markdown_value(accuracy.get("mae")),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Інтерпретація",
        "",
        "CPRI ранжує пріоритет поповнення запасу. «Закупити» включає страховий "
        "запас, розрахований із похибки прогнозу (MAE). SADI порівнює останній "
        "місяць із тим самим місяцем попередніх років. Значення є рекомендаціями "
        "для аналітика й мають перевірятися з урахуванням фактичних обмежень закупівлі.",
        "",
        "Джерело даних: локальна база BuildSales Insight; методику та походження "
        "демонстраційних/реальних даних описано в docs/data-sources.md.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_sales_csv(rows: list[dict], destination: str | Path) -> Path:
    """Save sales rows as a UTF-8 CSV with a BOM for spreadsheet compatibility."""
    path = Path(destination)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        labels = [label for _, label in EXPORT_COLUMNS]
        writer = csv.DictWriter(file, fieldnames=labels)
        writer.writeheader()
        for row in rows:
            writer.writerow({label: row.get(key, "") for key, label in EXPORT_COLUMNS})
    return path
