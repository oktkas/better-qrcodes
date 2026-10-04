#!/usr/bin/env python3
"""Build a deterministic KiCad Plugin and Content Manager archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "better_qr_codes"
METADATA_PATH = ROOT / "metadata.json"
PCM_ICON_PATH = ROOT / "resources" / "icon.png"
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
DOWNLOAD_FIELDS = {"download_url", "download_sha256", "download_size", "install_size"}


def read_metadata() -> dict:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    versions = metadata.get("versions", [])
    if len(versions) != 1:
        raise ValueError("Embedded metadata must describe exactly one version")
    if not versions[0].get("version"):
        raise ValueError("Embedded metadata has no release version")
    present = DOWNLOAD_FIELDS.intersection(versions[0])
    if present:
        raise ValueError(f"Embedded metadata contains repository-only fields: {sorted(present)}")
    return metadata


def package_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for source in PACKAGE_DIR.rglob("*"):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        relative = source.relative_to(PACKAGE_DIR).as_posix()
        if source.suffix != ".py" and relative != "icon.png":
            continue
        files.append((source, f"plugins/{relative}"))
    files.extend(
        [
            (ROOT / "LICENSE", "plugins/LICENSE"),
            (ROOT / "THIRD_PARTY_NOTICES.md", "plugins/THIRD_PARTY_NOTICES.md"),
            (PCM_ICON_PATH, "resources/icon.png"),
            (METADATA_PATH, "metadata.json"),
        ]
    )
    missing = [str(path) for path, _ in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing release files: {', '.join(missing)}")
    return sorted(files, key=lambda item: item[1])


def write_archive(destination: Path, files: list[tuple[Path, str]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, archive_name in files:
            info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)


def release_details(archive: Path, files: list[tuple[Path, str]], metadata: dict) -> dict:
    return {
        "identifier": metadata["identifier"],
        "version": metadata["versions"][0]["version"],
        "archive": archive.name,
        "download_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "download_size": archive.stat().st_size,
        "install_size": sum(source.stat().st_size for source, _ in files),
    }


def repository_metadata(metadata: dict, details: dict, download_url: str) -> dict:
    result = json.loads(json.dumps(metadata))
    version = result["versions"][0]
    version.update(
        {
            "download_url": download_url,
            "download_sha256": details["download_sha256"],
            "download_size": details["download_size"],
            "install_size": details["install_size"],
        }
    )
    return result


def build(output_dir: Path, download_url: str | None = None) -> tuple[Path, dict]:
    metadata = read_metadata()
    version = metadata["versions"][0]["version"]
    files = package_files()
    archive_name = f"better-qrcodes-{version}-pcm.zip"

    with tempfile.TemporaryDirectory(prefix="better-qrcodes-") as temporary:
        temporary_archive = Path(temporary) / archive_name
        write_archive(temporary_archive, files)
        output_dir.mkdir(parents=True, exist_ok=True)
        archive = output_dir / archive_name
        shutil.copyfile(temporary_archive, archive)

    details = release_details(archive, files, metadata)
    details_path = output_dir / f"better-qrcodes-{version}-release.json"
    details_path.write_text(json.dumps(details, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if download_url:
        repository_path = output_dir / f"better-qrcodes-{version}-repository-metadata.json"
        repository_path.write_text(
            json.dumps(repository_metadata(metadata, details, download_url), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return archive, details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--download-url",
        help="also write official-repository metadata using this public archive URL",
    )
    args = parser.parse_args()
    archive, details = build(args.output_dir.resolve(), args.download_url)
    print(f"Built {archive}")
    print(f"SHA-256: {details['download_sha256']}")
    print(f"Download size: {details['download_size']} bytes")
    print(f"Install size: {details['install_size']} bytes")


if __name__ == "__main__":
    main()
