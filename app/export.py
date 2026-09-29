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
