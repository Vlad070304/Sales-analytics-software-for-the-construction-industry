import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class CsvImportTests(unittest.TestCase):
    def test_imports_valid_rows_and_skips_invalid_ones(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT); CREATE TABLE sales(sold_at TEXT, material_id INTEGER, manager TEXT, customer TEXT, quantity REAL, unit_price REAL);")
        conn.execute("INSERT INTO materials VALUES (1, 'Цемент М500')")
        content = (
            "sold_at,material,manager,customer,quantity,unit_price\n"
            "2026-09-21,Цемент М500,Тест Менеджер,ТОВ Тест,12.5,190\n"
            "wrong-date,Невідомий,Тест,ТОВ Тест,3,100\n"
        )
        with patch.object(Path, "read_text", return_value=content), patch.object(database, "connection", return_value=conn), patch.object(database, "backup_database"), patch.object(database, "log_event"):
            report = database.preview_sales_csv("sales.csv")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)
            inserted = database.save_import_records(report["records"])
        self.assertEqual(inserted, 1)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
        conn.close()

    def test_rejects_csv_with_missing_columns(self):
        with patch.object(Path, "read_text", return_value="date,value\n2026-09-21,5\n"):
            with self.assertRaises(ValueError):
                database.preview_sales_csv("broken.csv")
