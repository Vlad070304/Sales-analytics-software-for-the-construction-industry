"""SQLite storage and reproducible demonstration dataset."""
from __future__ import annotations

import sqlite3
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
