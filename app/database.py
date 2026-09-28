"""SQLite storage and reproducible demonstration dataset."""

from __future__ import annotations

import sqlite3
import csv
import shutil
import json
from math import isfinite
from datetime import date, datetime
from pathlib import Path

from app.analytics import CPRI_WEIGHTS, validate_weights

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "buildsales.sqlite3"


def backup_database(label: str = "manual") -> Path:
    """Create a timestamped local copy of the SQLite database."""
    if not DATABASE_PATH.exists():
        raise ValueError("Базу даних ще не створено.")
    safe_label = "".join(char if char.isalnum() or char in "-_" else "-" for char in label)
    target_dir = DATABASE_PATH.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = target_dir / f"buildsales-{safe_label}-{timestamp}.sqlite3"
    shutil.copy2(DATABASE_PATH, target)
    return target


def connection() -> sqlite3.Connection:
    """Open a row-addressable connection to the local SQLite database."""
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    """Create the storage schema and populate an empty database with demonstration data."""
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
            CREATE TABLE IF NOT EXISTS audit_log (
              id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
              event_type TEXT NOT NULL, details TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_settings (
              setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0:
            seed(conn)


def seed(conn: sqlite3.Connection) -> None:
    """Populate a new database with reproducible construction-sales demonstration data."""
    materials = [
        ("Цемент М500", "Сухі суміші", "мішок", 260, 10),
        ("Арматура A500C", "Металопрокат", "т", 35, 21),
        ("Газоблок D500", "Стінові матеріали", "м³", 180, 14),
        ("Бітумна черепиця", "Покрівля", "м²", 460, 18),
    ]
    conn.executemany(
        "INSERT INTO materials(name, category, unit, stock, lead_time_days) VALUES (?, ?, ?, ?, ?)",
        materials,
    )
    base = [
        (1, "Ірина Коваль", "ТОВ Будмонтаж", 95.0),
        (2, "Олег Марченко", "ПП Фасад", 1.7),
        (3, "Ірина Коваль", "ЖК Весна", 42.0),
        (4, "Наталія Бойко", "Покрівля Плюс", 110.0),
    ]
    prices = {1: 182.0, 2: 36500.0, 3: 2450.0, 4: 310.0}
    rows = []
    for month in range(1, 13):
        season = [
            0.62,
            0.68,
            0.85,
            1.12,
            1.25,
            1.30,
            1.22,
            1.12,
            1.05,
            0.94,
            0.72,
            0.60,
        ][month - 1]
        for material_id, manager, customer, amount in base:
            quantity = round(amount * season * (1 + month * 0.018), 2)
            rows.append(
                (
                    date(2025, month, 12).isoformat(),
                    material_id,
                    manager,
                    customer,
                    quantity,
                    prices[material_id],
                )
            )
            rows.append(
                (
                    date(2026, month, 18).isoformat(),
                    material_id,
                    manager,
                    customer,
                    round(quantity * 1.10, 2),
                    prices[material_id] * 1.04,
                )
            )
    conn.executemany(
        "INSERT INTO sales("
        "sold_at, material_id, manager, customer, quantity, unit_price"
        ") VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )


def fetch_materials() -> list[dict]:
    """Return all materials in alphabetical order."""
    with connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM materials ORDER BY name")]


def log_event(event_type: str, details: str) -> None:
    """Record a user-visible data-management event."""
    with connection() as conn:
        conn.execute(
            "INSERT INTO audit_log(created_at, event_type, details) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), event_type, details),
        )


def fetch_events(limit: int = 100) -> list[dict]:
    """Return the most recent audit-log entries."""
    with connection() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        ]


def get_cpri_weights() -> dict[str, float]:
    """Return persisted CPRI weights or the default expert configuration."""
    with connection() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key=?",
            ("cpri_weights",),
        ).fetchone()
    if row is None:
        return dict(CPRI_WEIGHTS)
    try:
        return validate_weights(json.loads(row["setting_value"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(CPRI_WEIGHTS)


def save_cpri_weights(weights: dict[str, float]) -> None:
    """Validate, persist, and audit a custom CPRI weight configuration."""
    validated = validate_weights(weights)
    with connection() as conn:
        conn.execute(
            "INSERT INTO app_settings(setting_key, setting_value) VALUES (?, ?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
            ("cpri_weights", json.dumps(validated)),
        )
    log_event("cpri_weights", json.dumps(validated, ensure_ascii=False))


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
    """Validate and persist a new material, returning its identifier."""
    values = validate_material(payload)
    try:
        with connection() as conn:
            return conn.execute(
                "INSERT INTO materials("
                "name, category, unit, stock, lead_time_days"
                ") VALUES (?, ?, ?, ?, ?)",
                values,
            ).lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("Матеріал із такою назвою вже існує.") from error


def update_material(material_id: int, payload: dict) -> None:
    """Validate and update an existing material."""
    values = validate_material(payload)
    try:
        with connection() as conn:
            if (
                conn.execute(
                    "UPDATE materials SET name=?, category=?, unit=?, stock=?, "
                    "lead_time_days=? WHERE id=?",
                    (*values, material_id),
                ).rowcount
                == 0
            ):
                raise ValueError("Матеріал не знайдено.")
    except sqlite3.IntegrityError as error:
        raise ValueError("Матеріал із такою назвою вже існує.") from error


def delete_material(material_id: int) -> None:
    """Delete a material only when it has no sales history."""
    with connection() as conn:
        if conn.execute(
            "SELECT COUNT(*) FROM sales WHERE material_id=?", (material_id,)
        ).fetchone()[0]:
            raise ValueError("Неможливо видалити матеріал, для якого вже є продажі.")
        if conn.execute("DELETE FROM materials WHERE id=?", (material_id,)).rowcount == 0:
            raise ValueError("Матеріал не знайдено.")


def _parse_number(value: object, label: str, allow_zero: bool = False) -> float:
    """Parse a decimal typed with a dot or a comma; reject NaN, infinity and out-of-range values."""
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError as error:
        raise ValueError(f"{label} має бути числом.") from error
    if not isfinite(number):
        raise ValueError(f"{label} має бути скінченним числом.")
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(
            f"{label} не може бути від'ємною."
            if allow_zero
            else f"{label} має бути більшою за нуль."
        )
    return number


def validate_sale(payload: dict) -> tuple[str, int, str, str, float, float]:
    """Normalize and validate a manually entered sale before persistence."""
    manager = str(payload.get("manager") or "").strip()
    customer = str(payload.get("customer") or "").strip()
    if not manager or not customer or payload.get("material_id") in (None, ""):
        raise ValueError("Заповніть усі поля продажу.")
    try:
        sold_at = date.fromisoformat(str(payload.get("sold_at") or "").strip()).isoformat()
    except ValueError as error:
        raise ValueError("Дата має бути у форматі РРРР-ММ-ДД.") from error
    try:
        material_id = int(payload["material_id"])
    except (TypeError, ValueError) as error:
        raise ValueError("Некоректний матеріал.") from error
    quantity = _parse_number(payload.get("quantity"), "Кількість")
    unit_price = _parse_number(payload.get("unit_price"), "Ціна", allow_zero=True)
    return sold_at, material_id, manager, customer, quantity, unit_price


def add_sale(payload: dict) -> int:
    """Validate and persist a manually entered sale."""
    sold_at, material_id, manager, customer, quantity, unit_price = validate_sale(payload)
    with connection() as conn:
        if conn.execute("SELECT 1 FROM materials WHERE id=?", (material_id,)).fetchone() is None:
            raise ValueError("Матеріал не знайдено.")
        return conn.execute(
            "INSERT INTO sales("
            "sold_at, material_id, manager, customer, quantity, unit_price"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (sold_at, material_id, manager, customer, quantity, unit_price),
        ).lastrowid


def _sale_key(
    sold_at: str, customer: str, material_id: int, quantity: float, unit_price: float
) -> tuple:
    """Identity of a deal for duplicate detection: date, customer, material and total amount."""
    return (
        sold_at,
        customer.strip().casefold(),
        material_id,
        round(quantity * unit_price, 2),
    )


def preview_sales_csv(file_path: str | Path) -> dict:
    """Parse and validate CSV rows without changing the database.

    Rows that repeat a deal already stored in the database, or an earlier row
    of the same file, are reported as duplicates and excluded from ``records``.
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
    records: list[dict] = []
    errors: list[str] = []
    with connection() as conn:
        material_ids = {
            row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM materials")
        }
        for line_number, row in enumerate(reader, start=2):
            try:
                sold_at = (row["sold_at"] or "").strip()
                try:
                    date.fromisoformat(sold_at)
                except ValueError:
                    raise ValueError("дата має бути у форматі РРРР-ММ-ДД") from None
                material_name = (row["material"] or "").strip()
                if material_name not in material_ids:
                    raise ValueError(f"матеріал «{material_name}» відсутній у довіднику")
                material_id = material_ids[material_name]
                manager = (row["manager"] or "").strip()
                customer = (row["customer"] or "").strip()
                try:
                    quantity = float((row["quantity"] or "").replace(",", "."))
                    unit_price = float((row["unit_price"] or "").replace(",", "."))
                except ValueError:
                    raise ValueError("кількість і ціна мають бути числами") from None
                if (
                    not manager
                    or not customer
                    or not isfinite(quantity)
                    or not isfinite(unit_price)
                    or quantity <= 0
                    or unit_price < 0
                ):
                    raise ValueError("некоректні текстові або числові дані")
                records.append(
                    {
                        "sold_at": sold_at,
                        "material": material_name,
                        "material_id": material_id,
                        "manager": manager,
                        "customer": customer,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "line": line_number,
                    }
                )
            except ValueError as error:
                errors.append(f"рядок {line_number}: {error}")
        stored: set[tuple] = set()
        if records:
            dates = [record["sold_at"] for record in records]
            stored = {
                _sale_key(
                    row["sold_at"],
                    row["customer"],
                    row["material_id"],
                    row["quantity"],
                    row["unit_price"],
                )
                for row in conn.execute(
                    "SELECT sold_at, customer, material_id, quantity, unit_price "
                    "FROM sales WHERE sold_at BETWEEN ? AND ?",
                    (min(dates), max(dates)),
                )
            }
    unique: list[dict] = []
    duplicate_details: list[str] = []
    seen_in_file: set[tuple] = set()
    for record in records:
        key = _sale_key(
            record["sold_at"],
            record["customer"],
            record["material_id"],
            record["quantity"],
            record["unit_price"],
        )
        if key in stored:
            duplicate_details.append(f"рядок {record['line']}: така угода вже є в базі")
        elif key in seen_in_file:
            duplicate_details.append(f"рядок {record['line']}: повтор попереднього рядка файлу")
        else:
            seen_in_file.add(key)
            unique.append(record)
    return {
        "records": unique,
        "valid": len(unique),
        "skipped": len(errors),
        "errors": errors,
        "duplicates": len(duplicate_details),
        "duplicate_details": duplicate_details,
    }


def save_import_records(records: list[dict]) -> int:
    """Persist records previously returned by preview_sales_csv in one transaction."""
    if not records:
        return 0
    values = [
        (
            row["sold_at"],
            row["material_id"],
            row["manager"],
            row["customer"],
            row["quantity"],
            row["unit_price"],
        )
        for row in records
    ]
    backup_database("before-import")
    with connection() as conn:
        conn.executemany(
            "INSERT INTO sales("
            "sold_at, material_id, manager, customer, quantity, unit_price"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            values,
        )
    log_event("csv_import", f"Імпортовано записів: {len(values)}")
    return len(values)


def import_sales_csv(file_path: str | Path) -> dict:
    """Compatibility helper that previews and immediately saves valid CSV rows."""
    report = preview_sales_csv(file_path)
    report["inserted"] = save_import_records(report["records"])
    return report
