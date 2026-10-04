import tempfile
import unittest
from pathlib import Path

from better_qr_codes.model import QrSettings
from better_qr_codes.preferences import load_last_settings, save_last_settings


class PreferencesTests(unittest.TestCase):
    def test_round_trip_remembers_controls_but_not_content(self):
        settings = QrSettings(
            "private payload",
            "H",
            22.5,
            "B.Silkscreen",
            35,
            True,
            2,
            80,
            60,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_last_settings(settings, path)
            loaded = load_last_settings("F.Silkscreen", {"F.Silkscreen", "B.Silkscreen"}, path)

        self.assertEqual(loaded.data, "https://example.com")
        self.assertEqual(loaded.error_correction, settings.error_correction)
        self.assertEqual(loaded.size_mm, settings.size_mm)
        self.assertEqual(loaded.layer_name, settings.layer_name)
        self.assertEqual(loaded.corner_radius_percent, settings.corner_radius_percent)
        self.assertEqual(loaded.finder_radius_percent, settings.finder_radius_percent)
        self.assertEqual(loaded.knockout, settings.knockout)
        self.assertEqual(loaded.knockout_margin_modules, settings.knockout_margin_modules)
        self.assertEqual(loaded.knockout_corner_radius_percent, settings.knockout_corner_radius_percent)

    def test_missing_or_inactive_layer_uses_new_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            loaded = load_last_settings("F.Silkscreen", {"F.Silkscreen"}, path)

        self.assertEqual(loaded.error_correction, "L")
        self.assertEqual(loaded.size_mm, 15.0)
        self.assertEqual(loaded.layer_name, "F.Silkscreen")


if __name__ == "__main__":
    unittest.main()
