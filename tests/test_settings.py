"""Tests for persisted CPRI settings."""

import sqlite3
import unittest
from unittest.mock import patch

from app import database
from app.analytics import CPRI_WEIGHTS


class CpriSettingsTests(unittest.TestCase):
    """Verify CPRI weights are read and saved safely."""

    def setUp(self) -> None:
        """Prepare in-memory settings and audit tables."""
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            "CREATE TABLE app_settings(setting_key TEXT PRIMARY KEY, setting_value TEXT);"
            "CREATE TABLE audit_log("
            "id INTEGER PRIMARY KEY, created_at TEXT, event_type TEXT, details TEXT"
            ");"
        )
        self.patch = patch.object(database, "connection", return_value=self.conn)
        self.patch.start()

    def tearDown(self) -> None:
        """Close the in-memory database."""
        self.patch.stop()
        self.conn.close()

    def test_uses_expert_defaults_when_no_configuration_exists(self) -> None:
        """Defaults are available in a newly created database."""
        self.assertEqual(database.get_cpri_weights(), CPRI_WEIGHTS)

    def test_saves_valid_custom_weights(self) -> None:
        """Custom configuration can be retrieved and creates an audit entry."""
        weights = {"demand": 0.5, "volatility": 0.2, "lead": 0.2, "seasonality": 0.1}
        database.save_cpri_weights(weights)
        self.assertEqual(database.get_cpri_weights(), weights)
        event = self.conn.execute("SELECT event_type FROM audit_log").fetchone()
        self.assertEqual(event["event_type"], "cpri_weights")
