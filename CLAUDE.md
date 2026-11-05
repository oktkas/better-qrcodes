# Better QR Codes

## Project

A KiCad plugin that generates customizable QR codes for PCB designs. The goal is to improve on KiCad's native QR-code implementation with features such as rounded corners and thinner knockouts while preserving reliable scanning.

## Guidelines

- Keep the plugin simple and focused on QR-code generation in KiCad.
- Prioritize scan reliability over appearance.
- Preserve required QR structures, including finder patterns and the quiet zone.
- Treat non-standard styling as intentional and document its tradeoffs.
- Keep `README.md` installation and usage instructions current once those workflows exist.
- Treat `FEATURES.md` as the product backlog and keep implemented behavior consistent with it.

## Current state

The first implementation targets KiCad 10 as a Python Action Plugin. Each QR code is a board-only `FOOTPRINT` (board-only, excluded from BOM and position files, hidden `QR<n>` reference, empty library nickname so DRC does not report a missing library) whose `PCB_SHAPE` children are the artwork. Compressed, versioned settings (`BQR2:`, including size) live in its hidden `Better QR Codes` field. KiCad owns position, orientation and side so they appear in the Properties panel and survive native move/rotate/flip; the plugin reads them back instead of storing them. Artwork is always rebuilt front-side at orientation 0, then flipped and rotated by KiCad. Legacy 0.1.x `PCB_GROUP` codes (`BQR1:` in the group name) are converted to footprints on their first edit. Settings include separate data/finder radii, module-based knockout margin, and knockout background radius. Finder rounding applies to the complete outer/gap/center geometry and spans the full finder size; the gap radius is a one-module inset from the outer radius so the ring stays visually constant in width. Do not replace this representation with `PCB_BARCODE`; styling features need control over the rendered geometry.

The dialog reads the active KiCad PCB color theme for layer swatches and uses a fixed dark preview background for reliable contrast. Board output and preview must both use `geometry.material_polygons()` so they cannot disagree; the preview places it with `model.place_polygons()`, which mirrors KiCad's footprint transform (a test compares the two). A global wx event filter routes canvas double-clicks on plugin-owned footprints (and legacy groups) to the editor instead of KiCad's footprint dialog, because custom `PCB_GENERATOR` items are not exposed by KiCad's Python API.

Picking a new code up with the cursor uses the IPC API's `InteractiveMoveItems` through `better_qr_codes/ipc.py`, a dependency-free NNG/protobuf client (the SWIG API cannot start tools, and a PCM package cannot install `kicad-python`'s compiled `pynng`). It must run off KiCad's main thread, which answers API requests.

Complex knockout results must be fractured into simple, hole-free `PCB_SHAPE` polygons before insertion. KiCad's interactive scale tool can corrupt a complex polygon's hole contours.

Updating artwork detaches old items and retains their wrappers for the KiCad process lifetime. Do not eagerly delete them: KiCad's selection tool can briefly retain native pointers after the modal dialog closes, causing access violations if those objects are destroyed.

The QR encoder is the vendored MIT-licensed Project Nayuki implementation in `better_qr_codes/vendor/qrcodegen.py`. Keep its license header intact.

Run model tests with:

```text
python -m unittest discover -s tests
```

The board and geometry tests skip without `pcbnew`. On Windows, run them with KiCad's Python from the repo root (it ignores `PYTHONPATH`, so do not use `-I`):

```text
BETTER_QR_CODES_NO_REGISTER=1 "C:\Program Files\KiCad\10.0\bin\python.exe" -m unittest discover -s tests
```

## Releases

The single release version source is the version entry in `metadata.json`. Build the deterministic KiCad PCM archive with `python scripts/build_release.py`. The archive must contain plugin files directly under `plugins/`, a 24×24 toolbar icon there, a 64×64 PCM icon under `resources/`, and embedded metadata without `download_*` fields. Set `BETTER_QR_CODES_NO_REGISTER=1` when testing with KiCad's Python. See `RELEASING.md` for the release checklist and official repository submission flow.
