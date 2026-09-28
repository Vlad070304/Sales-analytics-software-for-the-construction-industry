"""SQLite storage and reproducible demonstration dataset."""
from __future__ import annotations

import sqlite3
import csv
from datetime import date
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "buildsales.sqlite3"


def connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS materials (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
              category TEXT NOT NULL, unit TEXT NOT NULL,
              stock REAL NOT NULL, lead_time_days INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sales (
              id INTEGER PRIMARY KEY, sold_at TEXT NOT NULL,
              material_id INTEGER NOT NULL REFERENCES materials(id),
              manager TEXT NOT NULL, customer TEXT NOT NULL,
              quantity REAL NOT NULL CHECK(quantity > 0),
              unit_price REAL NOT NULL CHECK(unit_price >= 0)
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0:
            seed(conn)


def seed(conn: sqlite3.Connection) -> None:
    materials = [
        ("Цемент М500", "Сухі суміші", "мішок", 260, 10),
        ("Арматура A500C", "Металопрокат", "т", 35, 21),
        ("Газоблок D500", "Стінові матеріали", "м³", 180, 14),
        ("Бітумна черепиця", "Покрівля", "м²", 460, 18),
    ]
    conn.executemany(
        "INSERT INTO materials(name, category, unit, stock, lead_time_days) VALUES (?, ?, ?, ?, ?)", materials
    )
    base = [(1, "Ірина Коваль", "ТОВ Будмонтаж", 95.0), (2, "Олег Марченко", "ПП Фасад", 1.7),
            (3, "Ірина Коваль", "ЖК Весна", 42.0), (4, "Наталія Бойко", "Покрівля Плюс", 110.0)]
    prices = {1: 182.0, 2: 36500.0, 3: 2450.0, 4: 310.0}
    rows = []
    for month in range(1, 13):
        season = [0.62, 0.68, 0.85, 1.12, 1.25, 1.30, 1.22, 1.12, 1.05, 0.94, 0.72, 0.60][month - 1]
        for material_id, manager, customer, amount in base:
            quantity = round(amount * season * (1 + month * 0.018), 2)
            rows.append((date(2025, month, 12).isoformat(), material_id, manager, customer, quantity, prices[material_id]))
            rows.append((date(2026, month, 18).isoformat(), material_id, manager, customer, round(quantity * 1.10, 2), prices[material_id] * 1.04))
    conn.executemany(
        "INSERT INTO sales(sold_at, material_id, manager, customer, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)", rows
    )


def fetch_materials() -> list[dict]:
    with connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM materials ORDER BY name")]


def validate_material(payload: dict) -> tuple[str, str, str, float, int]:
    """Normalize and validate a material record before persistence."""
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "")).strip()
    unit = str(payload.get("unit", "")).strip()
    if not name or not category or not unit:
        raise ValueError("Назва, категорія та одиниця виміру є обов'язковими.")
    try:
        stock = float(payload.get("stock"))
        lead_time_days = int(payload.get("lead_time_days"))
    except (TypeError, ValueError) as error:
        raise ValueError("Запас і строк постачання мають бути числами.") from error
    if stock < 0 or lead_time_days < 0:
        raise ValueError("Запас і строк постачання не можуть бути від'ємними.")
    return name, category, unit, stock, lead_time_days


def add_material(payload: dict) -> int:
    values = validate_material(payload)
    try:
        with connection() as conn:
            return conn.execute(
                "INSERT INTO materials(name, category, unit, stock, lead_time_days) VALUES (?, ?, ?, ?, ?)", values
            ).lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("Матеріал із такою назвою вже існує.") from error


def update_material(material_id: int, payload: dict) -> None:
    values = validate_material(payload)
    try:
        with connection() as conn:
            if conn.execute("UPDATE materials SET name=?, category=?, unit=?, stock=?, lead_time_days=? WHERE id=?", (*values, material_id)).rowcount == 0:
                raise ValueError("Матеріал не знайдено.")
    except sqlite3.IntegrityError as error:
        raise ValueError("Матеріал із такою назвою вже існує.") from error


def delete_material(material_id: int) -> None:
    with connection() as conn:
        if conn.execute("SELECT COUNT(*) FROM sales WHERE material_id=?", (material_id,)).fetchone()[0]:
            raise ValueError("Неможливо видалити матеріал, для якого вже є продажі.")
        if conn.execute("DELETE FROM materials WHERE id=?", (material_id,)).rowcount == 0:
            raise ValueError("Матеріал не знайдено.")


def add_sale(payload: dict) -> int:
    required = ("sold_at", "material_id", "manager", "customer", "quantity", "unit_price")
    if not all(payload.get(field) not in (None, "") for field in required):
        raise ValueError("Заповніть усі поля продажу.")
    with connection() as conn:
        cursor = conn.execute(
            "INSERT INTO sales(sold_at, material_id, manager, customer, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
            tuple(payload[field] for field in required),
        )
        return cursor.lastrowid


def import_sales_csv(file_path: str | Path) -> dict:
    """Import validated sales from a UTF-8 or Windows-1251 CSV file.

    Required columns: sold_at, material, manager, customer, quantity, unit_price.
    The entire file is transactional: if no records are valid, the database is unchanged.
    """
    required = {"sold_at", "material", "manager", "customer", "quantity", "unit_price"}
    path = Path(file_path)
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="cp1251")
    reader = csv.DictReader(content.splitlines())
    headers = set(reader.fieldnames or [])
    if not required.issubset(headers):
        missing = ", ".join(sorted(required - headers))
        raise ValueError(f"У CSV відсутні обов'язкові колонки: {missing}.")
    prepared: list[tuple] = []
    errors: list[str] = []
    with connection() as conn:
        material_ids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM materials")}
        for line_number, row in enumerate(reader, start=2):
            try:
                sold_at = (row["sold_at"] or "").strip()
                date.fromisoformat(sold_at)
                material_id = material_ids[(row["material"] or "").strip()]
                manager = (row["manager"] or "").strip()
                customer = (row["customer"] or "").strip()
                quantity = float((row["quantity"] or "").replace(",", "."))
                unit_price = float((row["unit_price"] or "").replace(",", "."))
                if not manager or not customer or quantity <= 0 or unit_price < 0:
                    raise ValueError("некоректні текстові або числові дані")
                prepared.append((sold_at, material_id, manager, customer, quantity, unit_price))
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"рядок {line_number}: {error}")
        if prepared:
            conn.executemany(
                "INSERT INTO sales(sold_at, material_id, manager, customer, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
                prepared,
            )
    return {"inserted": len(prepared), "skipped": len(errors), "errors": errors}
