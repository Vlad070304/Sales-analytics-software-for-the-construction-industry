"""Tests for local sales export."""

import io
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app.export import (
    anonymize_sales_rows,
    create_sales_import_template,
    export_analytics_report,
    export_sales_csv,
)


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

    def test_import_template_contains_only_required_columns(self) -> None:
        """The generated template is accepted as the starting point for an import file."""
        output = NonClosingStringIO()
        with patch.object(Path, "open", return_value=output):
            result = create_sales_import_template("import-template.csv")
        self.assertEqual(result, Path("import-template.csv"))
        self.assertEqual(
            output.getvalue().lstrip("\ufeff").strip(),
            "sold_at,material,manager,customer,quantity,unit_price",
        )

    def test_analytics_report_includes_metrics_filters_and_recommendations(self) -> None:
        """Research report records the selected data and explainable recommendations."""
        materials = [
            {
                "name": "Цемент М500",
                "forecast": [{"quantity": 120.0}],
                "risk": {"score": 74.2},
                "procurement": {"order_quantity": 34.5, "confidence": 81.0},
                "anomaly": {"score": 20.0, "direction": "зростання"},
                "accuracy": {"mae": 8.2},
            }
        ]
        with patch.object(Path, "write_text", return_value=None) as write_text:
            result = export_analytics_report(
                {"revenue": 12000, "deals": 5, "materials": 1, "high_risk": 1},
                materials,
                {"Матеріал": "Цемент М500"},
                "analytics.md",
                created_at=datetime(2026, 9, 30, 12, 0),
            )
        report = write_text.call_args.args[0]
        self.assertEqual(result, Path("analytics.md"))
        self.assertIn("2026-09-30 12:00", report)
        self.assertIn("Виручка: **12,000.00 ₴**", report)
        self.assertIn("Цемент М500", report)
        self.assertIn("+20.0% (зростання)", report)
