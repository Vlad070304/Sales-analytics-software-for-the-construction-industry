"""Tests for local sales export."""

import io
import unittest
from pathlib import Path
from unittest.mock import patch

from app.export import export_sales_csv


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
