import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class CsvImportTests(unittest.TestCase):
    def test_imports_valid_rows_and_skips_invalid_ones(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            "CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE sales("
            "sold_at TEXT, material_id INTEGER, manager TEXT, customer TEXT, "
            "quantity REAL, unit_price REAL"
            ");"
        )
        conn.execute("INSERT INTO materials VALUES (1, 'Цемент М500')")
        content = (
            "sold_at,material,manager,customer,quantity,unit_price\n"
            "2026-09-21,Цемент М500,Тест Менеджер,ТОВ Тест,12.5,190\n"
            "wrong-date,Невідомий,Тест,ТОВ Тест,3,100\n"
        )
        with (
            patch.object(Path, "read_text", return_value=content),
            patch.object(database, "connection", return_value=conn),
            patch.object(database, "backup_database"),
            patch.object(database, "log_event"),
        ):
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


class CsvPreviewCase(unittest.TestCase):
    HEADER = "sold_at,material,manager,customer,quantity,unit_price\n"

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            "CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE sales("
            "id INTEGER PRIMARY KEY, sold_at TEXT, material_id INTEGER, "
            "manager TEXT, customer TEXT, quantity REAL, unit_price REAL"
            ");"
            "INSERT INTO materials VALUES (1, 'Цемент М500');"
            "INSERT INTO sales("
            "sold_at, material_id, manager, customer, quantity, unit_price"
            ") VALUES ('2026-09-21', 1, 'Хтось', 'ТОВ Тест', 10, 190);"
        )

    def tearDown(self):
        self.conn.close()

    def preview(self, rows: str) -> dict:
        with (
            patch.object(Path, "read_text", return_value=self.HEADER + rows),
            patch.object(database, "connection", return_value=self.conn),
        ):
            return database.preview_sales_csv("sales.csv")


class DuplicateDetectionTests(CsvPreviewCase):
    def test_skips_rows_already_stored_in_database(self):
        report = self.preview("2026-09-21,Цемент М500,Інший менеджер,тов тест,20,95\n")
        self.assertEqual(report["duplicates"], 1)
        self.assertEqual(report["valid"], 0)
        self.assertEqual(report["skipped"], 0)
        self.assertEqual(report["duplicate_details"], ["рядок 2: така угода вже є в базі"])

    def test_skips_repeated_rows_inside_the_file(self):
        report = self.preview(
            "2026-09-22,Цемент М500,Тест,ТОВ Інший,5,190\n"
            "2026-09-22,Цемент М500,Тест,ТОВ Інший,5,190\n"
        )
        self.assertEqual((report["valid"], report["duplicates"]), (1, 1))
        self.assertEqual(report["duplicate_details"], ["рядок 3: повтор попереднього рядка файлу"])

    def test_different_amount_is_not_a_duplicate(self):
        report = self.preview("2026-09-21,Цемент М500,Тест,ТОВ Тест,11,190\n")
        self.assertEqual((report["valid"], report["duplicates"]), (1, 0))


class ImportErrorMessageTests(CsvPreviewCase):
    def test_row_errors_are_readable(self):
        report = self.preview(
            "вчора,Цемент М500,Тест,ТОВ,1,1\n"
            "2026-09-22,Невідомий,Тест,ТОВ,1,1\n"
            "2026-09-22,Цемент М500,Тест,ТОВ,abc,1\n"
        )
        self.assertEqual(report["skipped"], 3)
        self.assertEqual(report["errors"][0], "рядок 2: дата має бути у форматі РРРР-ММ-ДД")
        self.assertEqual(report["errors"][1], "рядок 3: матеріал «Невідомий» відсутній у довіднику")
        self.assertEqual(report["errors"][2], "рядок 4: кількість і ціна мають бути числами")
