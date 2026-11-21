import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from threshold_settings import DEFAULT_THRESHOLD, load_threshold, save_threshold


class ThresholdSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        local = patch.dict(os.environ, {"LOCALAPPDATA": temporary.name})
        local.start()
        self.addCleanup(local.stop)
        self.path = Path(temporary.name) / "Auto-C" / "threshold.json"

    def test_absent_malformed_and_unreadable_default(self):
        self.assertEqual(load_threshold(), DEFAULT_THRESHOLD)
        self.path.parent.mkdir()
        for content in ('{"threshold":', '{}', '[]', '{"threshold": true}', '{"threshold": NaN}',
                        '{"threshold": 1}', '{"threshold": "-43"}'):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                self.assertEqual(load_threshold(), DEFAULT_THRESHOLD)
        with patch.object(Path, "open", side_effect=PermissionError):
            self.assertEqual(load_threshold(), DEFAULT_THRESHOLD)

    def test_fractional_and_boundary_values_survive_restarts(self):
        for value in (-96, -37.5, 0):
            with self.subTest(value=value):
                save_threshold(value)
                self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["threshold"], value)
                self.assertIsInstance(load_threshold(), float)
                self.assertEqual(load_threshold(), value)

    def test_invalid_save_or_failed_replace_preserves_old_value(self):
        save_threshold(-39)
        for value in (False, "0", float("nan"), float("inf"), float("-inf"), -97, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                save_threshold(value)
        with patch.object(Path, "replace", side_effect=PermissionError), self.assertRaises(PermissionError):
            save_threshold(-60)
        self.assertEqual(load_threshold(), -39)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
