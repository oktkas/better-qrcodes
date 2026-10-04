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

The first implementation targets KiCad 10 as a Python Action Plugin. It generates regular QR codes as grouped `PCB_SHAPE` artwork and stores compressed, versioned settings in the `PCB_GROUP` name so the plugin can edit and regenerate its own output. Settings include separate data/finder radii, module-based knockout margin, and knockout background radius. Finder rounding applies to the complete outer/gap/center geometry and spans the full finder size; the gap radius is a one-module inset from the outer radius so the ring stays visually constant in width. Do not replace this representation with `PCB_BARCODE`; styling features need control over the rendered geometry.

The dialog reads the active KiCad PCB color theme for layer swatches and uses a fixed dark preview background for reliable contrast. Board output and preview must both use `geometry.material_polygons()` so they cannot disagree. A global wx event filter routes canvas double-clicks on plugin-owned groups to the editor because custom `PCB_GENERATOR` items are not exposed by KiCad's Python API.

Complex knockout results must be fractured into simple, hole-free `PCB_SHAPE` polygons before insertion. KiCad's interactive scale tool can corrupt a complex polygon's hole contours.

Updating artwork detaches old items and retains their wrappers for the KiCad process lifetime. Do not eagerly delete them: KiCad's selection tool can briefly retain native pointers after the modal dialog closes, causing access violations if those objects are destroyed.

The QR encoder is the vendored MIT-licensed Project Nayuki implementation in `better_qr_codes/vendor/qrcodegen.py`. Keep its license header intact.

Run model tests with:

```text
python -m unittest discover -s tests
```

## Releases

The single release version source is the version entry in `metadata.json`. Build the deterministic KiCad PCM archive with `python scripts/build_release.py`. The archive must contain plugin files directly under `plugins/`, a 24×24 toolbar icon there, a 64×64 PCM icon under `resources/`, and embedded metadata without `download_*` fields. Set `BETTER_QR_CODES_NO_REGISTER=1` when testing with KiCad's Python. See `RELEASING.md` for the release checklist and official repository submission flow.
