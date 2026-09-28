import sqlite3
import unittest
from unittest.mock import patch

from app import database


class MaterialStorageTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            "CREATE TABLE materials("
            "id INTEGER PRIMARY KEY, name TEXT UNIQUE, category TEXT, unit TEXT, "
            "stock REAL, lead_time_days INTEGER"
            ");"
            "CREATE TABLE sales(id INTEGER PRIMARY KEY, material_id INTEGER);"
        )
        self.patch = patch.object(database, "connection", return_value=self.conn)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.conn.close()

    def test_add_and_update_material(self):
        material_id = database.add_material(
            {
                "name": "Пісок",
                "category": "Сипучі",
                "unit": "т",
                "stock": "12.5",
                "lead_time_days": "3",
            }
        )
        database.update_material(
            material_id,
            {
                "name": "Пісок кварцовий",
                "category": "Сипучі",
                "unit": "т",
                "stock": 14,
                "lead_time_days": 5,
            },
        )
        row = self.conn.execute(
            "SELECT name, stock, lead_time_days FROM materials WHERE id=?",
            (material_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("Пісок кварцовий", 14.0, 5))

    def test_cannot_delete_material_with_sales(self):
        material_id = database.add_material(
            {
                "name": "Щебінь",
                "category": "Сипучі",
                "unit": "т",
                "stock": 7,
                "lead_time_days": 2,
            }
        )
        self.conn.execute("INSERT INTO sales(material_id) VALUES (?)", (material_id,))
        with self.assertRaises(ValueError):
            database.delete_material(material_id)
