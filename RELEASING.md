# Releasing Better QR Codes

The project ships as a KiCad Plugin and Content Manager (PCM) ZIP. The single release version source is the version entry in `metadata.json`.

## Prepare a release

1. Update the version entry in `metadata.json`.
2. Move the release notes in `CHANGELOG.md` from `Unreleased` to the release date.
3. Run the complete test suite:

   ```text
   python -m unittest discover -s tests
   ```

   Run it once with normal Python and once with KiCad's Python so the board-geometry tests do not skip. Set `BETTER_QR_CODES_NO_REGISTER=1` for the KiCad run so importing the package does not register the toolbar action in a test process.

4. Build the deterministic package:

   ```text
   python scripts/build_release.py
   ```

   This creates the PCM archive and its checksum/size report in `dist/`.

5. In KiCad 10, open **Plugin and Content Manager → Install from File**, select the `*-pcm.zip`, restart the PCB Editor, and complete the acceptance checks below.

## Publish

1. Commit the prepared release and create an annotated `v<version>` tag.
2. Push the commit and tag. The tag workflow in `.github/workflows/ci.yml` tests and builds the package, then creates the GitHub release with the PCM ZIP attached. To publish an existing tag again, run the **CI** workflow manually with `publish_tag` set.
3. Confirm that the release asset downloads successfully. Do not submit GitHub's automatic source archive as the PCM download.
4. Download the published PCM asset, then use that exact file and its permanent public URL to create repository metadata:

   ```text
   python scripts/build_release.py --download-url https://github.com/oktkas/better-qrcodes/releases/download/v<version>/better-qrcodes-<version>-pcm.zip --repository-archive path/to/downloaded/package.zip
   ```

5. Fork [KiCad's package metadata repository](https://gitlab.com/kicad/addons/metadata), create `packages/com.github.oktkas.better-qrcodes/`, and copy the generated `*-repository-metadata.json` there as `metadata.json`. Add `resources/icon.png` and open a merge request.

The metadata inside the ZIP intentionally has no `download_*` fields. The generated repository metadata adds the public URL, SHA-256, download size, and installed size required for submission. Always use the downloaded release asset for this step because ZIP compression can produce different container bytes across platforms. For later releases, retain previous version entries in KiCad's repository metadata and prepend the new version.

## Acceptance checks

- The package installs without warnings and adds one **Better QR Codes** toolbar action.
- A code can be placed on copper and technical layers and survives save/reopen.
- Rounded modules, rounded finders, knockout margins, and knockout rounding match the preview.
- A generated code scans at default settings.
- Selecting or double-clicking plugin artwork reopens it with the stored settings.
- Rotating (R, Move Exactly, Properties panel) and flipping a code, then editing it, keeps its placement.
- A code made by 0.1.x converts to a footprint on edit.
- Updating and interactively scaling normal and knockout artwork does not corrupt it.
- The plugin can be uninstalled cleanly through the PCM.
