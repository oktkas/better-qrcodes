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

The first implementation targets KiCad 10 as a Python Action Plugin. It generates regular QR codes as grouped `PCB_SHAPE` artwork and stores compressed, versioned settings in the `PCB_GROUP` name so the plugin can edit and regenerate its own output. Do not replace this representation with `PCB_BARCODE`; future styling features need control over the rendered geometry.

The dialog reads the active KiCad PCB color theme for its preview and layer swatches. A global wx event filter routes canvas double-clicks on plugin-owned groups to the editor because custom `PCB_GENERATOR` items are not exposed by KiCad's Python API.

The QR encoder is the vendored MIT-licensed Project Nayuki implementation in `better_qr_codes/vendor/qrcodegen.py`. Keep its license header intact.

Run model tests with:

```text
python -m unittest discover -s tests
```
