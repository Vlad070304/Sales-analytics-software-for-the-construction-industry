import sqlite3
import unittest
from unittest.mock import patch

from app import database


class AuditLogTests(unittest.TestCase):
    def test_records_and_returns_event(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE audit_log("
            "id INTEGER PRIMARY KEY, created_at TEXT, event_type TEXT, details TEXT"
            ")"
        )
        with patch.object(database, "connection", return_value=conn):
            database.log_event("csv_import", "Імпортовано записів: 2")
            events = database.fetch_events()
        self.assertEqual(events[0]["event_type"], "csv_import")
        self.assertEqual(events[0]["details"], "Імпортовано записів: 2")
        conn.close()
