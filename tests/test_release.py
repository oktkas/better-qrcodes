import hashlib
import importlib.util
import json
import shutil
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("build_release", SCRIPT_PATH)
build_release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_release)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


class ReleaseTests(unittest.TestCase):
    def test_metadata_matches_release_source(self):
        metadata = build_release.read_metadata()
        release = metadata["versions"][0]

        self.assertEqual("0.2.0", release["version"])
        self.assertEqual("com.github.oktkas.better-qrcodes", metadata["identifier"])
        self.assertEqual("Ondřej Kučera", metadata["author"]["name"])
        self.assertEqual("https://oktkas.cz/", metadata["author"]["contact"]["web"])
        self.assertEqual("MIT", metadata["license"])
        self.assertEqual("stable", release["status"])
        self.assertEqual("10.0", release["kicad_version"])
        self.assertEqual("swig", release["runtime"])
        self.assertFalse(build_release.DOWNLOAD_FIELDS.intersection(release))

    def test_icons_have_kicad_sizes(self):
        self.assertEqual((24, 24), png_size(ROOT / "better_qr_codes" / "icon.png"))
        self.assertEqual((64, 64), png_size(ROOT / "resources" / "icon.png"))

    def test_build_is_deterministic_and_has_pcm_layout(self):
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
            tempfile.TemporaryDirectory() as repository_output,
        ):
            archive, details = build_release.build(Path(first))
            other_archive, other_details = build_release.build(Path(second))

            self.assertEqual(archive.read_bytes(), other_archive.read_bytes())
            self.assertEqual(details["download_sha256"], other_details["download_sha256"])
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), details["download_sha256"])

            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
                self.assertIn("metadata.json", names)
                self.assertIn("resources/icon.png", names)
                self.assertIn("plugins/__init__.py", names)
                self.assertIn("plugins/icon.png", names)
                self.assertIn("plugins/LICENSE", names)
                self.assertIn("plugins/THIRD_PARTY_NOTICES.md", names)
                self.assertIn("plugins/vendor/qrcodegen.py", names)
                self.assertFalse(any("better_qr_codes/" in name for name in names))
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
                embedded = json.loads(package.read("metadata.json"))
                self.assertFalse(build_release.DOWNLOAD_FIELDS.intersection(embedded["versions"][0]))

            published_archive = Path(first) / "published.zip"
            shutil.copyfile(archive, published_archive)
            with zipfile.ZipFile(published_archive, "a") as published:
                published.comment = b"Different published container bytes"
            build_release.build(
                Path(repository_output),
                "https://example.test/package.zip",
                published_archive,
            )

            repository_path = Path(repository_output) / "better-qrcodes-0.2.0-repository-metadata.json"
            repository = json.loads(repository_path.read_text(encoding="utf-8"))
            release = repository["versions"][0]
            self.assertEqual("https://example.test/package.zip", release["download_url"])
            self.assertEqual(hashlib.sha256(published_archive.read_bytes()).hexdigest(), release["download_sha256"])
            self.assertEqual(published_archive.stat().st_size, release["download_size"])
            self.assertEqual(details["install_size"], release["install_size"])


if __name__ == "__main__":
    unittest.main()
