import sqlite3
import unittest
from unittest.mock import patch

from app import database


class ManualSaleTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            "CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE sales("
            "id INTEGER PRIMARY KEY, sold_at TEXT NOT NULL, material_id INTEGER NOT NULL,"
            "manager TEXT NOT NULL, customer TEXT NOT NULL,"
            "quantity REAL NOT NULL CHECK(quantity > 0),"
            "unit_price REAL NOT NULL CHECK(unit_price >= 0)"
            ");"
            "INSERT INTO materials VALUES (1, 'Цемент М500');"
        )
        self.patch = patch.object(database, "connection", return_value=self.conn)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.conn.close()

    def sale(self, **overrides):
        payload = {
            "sold_at": "2026-09-21",
            "material_id": 1,
            "manager": " Ірина Коваль ",
            "customer": "ТОВ Тест",
            "quantity": "12,5",
            "unit_price": "190",
        }
        return {**payload, **overrides}

    def test_saves_normalized_sale(self):
        sale_id = database.add_sale(self.sale())
        row = self.conn.execute(
            "SELECT sold_at, manager, quantity, unit_price FROM sales WHERE id=?",
            (sale_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("2026-09-21", "Ірина Коваль", 12.5, 190.0))

    def test_rejects_invalid_values_with_readable_errors(self):
        invalid = [
            {"sold_at": "21.09.2026"},
            {"quantity": "0"},
            {"quantity": "abc"},
            {"quantity": "inf"},
            {"unit_price": "-1"},
            {"unit_price": "nan"},
            {"manager": "   "},
            {"material_id": 999},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                database.add_sale(self.sale(**overrides))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)
