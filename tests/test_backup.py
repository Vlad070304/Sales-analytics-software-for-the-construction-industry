import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class BackupTests(unittest.TestCase):
    def test_creates_timestamped_copy_in_backups_directory(self):
        source = Path("C:/test-data/buildsales.sqlite3")
        with (
            patch.object(database, "DATABASE_PATH", source),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "mkdir"),
            patch("app.database.shutil.copy2") as copy,
        ):
            target = database.backup_database("before-import")
        self.assertEqual(copy.call_args.args[0], source)
        self.assertEqual(copy.call_args.args[1], target)
        self.assertEqual(target.parent.name, "backups")
        self.assertTrue(target.name.startswith("buildsales-before-import-"))
