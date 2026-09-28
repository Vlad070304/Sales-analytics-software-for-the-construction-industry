"""Local, dependency-free export helpers for BuildSales Insight."""

from __future__ import annotations

import csv
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


def export_sales_csv(rows: list[dict], destination: str | Path) -> Path:
    """Save sales rows as a UTF-8 CSV with a BOM for spreadsheet compatibility."""
    path = Path(destination)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        labels = [label for _, label in EXPORT_COLUMNS]
        writer = csv.DictWriter(file, fieldnames=labels)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {label: row.get(key, "") for key, label in EXPORT_COLUMNS}
            )
    return path
