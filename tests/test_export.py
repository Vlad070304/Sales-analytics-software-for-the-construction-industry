"""Tests for local sales export."""

import io
import unittest
from pathlib import Path
from unittest.mock import patch

from app.export import anonymize_sales_rows, export_sales_csv


class NonClosingStringIO(io.StringIO):
    """Keep text available after a context manager closes the export stream."""

    def close(self) -> None:
        """Avoid closing the in-memory stream used by this test."""


class CsvExportTests(unittest.TestCase):
    """Verify export content without writing files outside the test process."""

    def test_writes_header_and_sales_row(self) -> None:
        """Export contains the documented fields and computed values."""
        output = NonClosingStringIO()
        row = {
            "sold_at": "2026-09-25",
            "material": "Цемент М500",
            "category": "Сухі суміші",
            "manager": "Ірина Коваль",
            "customer": "ТОВ Будмонтаж",
            "quantity": 12.5,
            "unit_price": 190,
            "revenue": 2375,
        }
        with patch.object(Path, "open", return_value=output):
            result = export_sales_csv([row], "report.csv")
        self.assertEqual(result, Path("report.csv"))
        self.assertIn("Матеріал", output.getvalue())
        self.assertIn("Цемент М500", output.getvalue())

    def test_anonymization_preserves_relationships_without_source_names(self) -> None:
        """Aliases are stable while the export input remains unchanged."""
        rows = [
            {"manager": "Ірина Коваль", "customer": "ТОВ Будмонтаж", "quantity": 1},
            {"manager": "Ірина Коваль", "customer": "ТОВ Будмонтаж", "quantity": 2},
            {"manager": "Олег Марченко", "customer": "ПП Рембуд", "quantity": 3},
        ]
        result = anonymize_sales_rows(rows)
        self.assertEqual(result[0]["manager"], result[1]["manager"])
        self.assertEqual(result[0]["customer"], result[1]["customer"])
        self.assertNotEqual(result[0]["manager"], result[2]["manager"])
        self.assertNotIn("Ірина Коваль", {row["manager"] for row in result})
        self.assertEqual(rows[0]["customer"], "ТОВ Будмонтаж")
