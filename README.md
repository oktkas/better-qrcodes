# Better QR Codes

Better QR Codes is a KiCad plugin for creating more flexible, visually refined QR codes on PCB designs.

Improvements over KiCad's native QR-code generator include:

- Relative rounded corners that preserve connected modules
- Inverted knockout artwork with 4-module, 2-module, or custom margins
- Practical styling options that remain reliably scannable

These features may go beyond the original QR-code specification, but are widely supported by modern scanners.

## Current functionality

- Regular QR Code Model 2 symbols
- Content, error-correction, layer, and physical-size controls
- Relative 0–100% corner-radius control
- Back-side layers place the code flipped, upright when viewed from below (orientation 180°, as KiCad gives any flipped footprint); switching the layer between front and back in the dialog converts the orientation like KiCad's Flip
- One relative finder-rounding control with a constant-width outer ring and rounded center
- Optional knockout with margins measured in modules
- Independently rounded knockout background corners
- Active PCB layers, shown with the current KiCad theme colors
- Live preview using the selected layer color on a fixed dark PCB-style background
- Dashed four-module quiet-zone outline in the preview
- New codes default to 15 mm and low error correction
- Successful settings are remembered for the next new code
- Toolbar action in KiCad's PCB Editor
- Each code is a board-only footprint (`QR1`, `QR2`, …): position, orientation and side are in KiCad's Properties panel and work with R, Move Exactly and Flip
- Re-editing by double-clicking a code or opening the plugin with it selected; native moves, rotations and flips are kept
- Codes made by 0.1.x (groups) are converted to footprints the first time they are edited

## Install

Better QR Codes requires KiCad 10.

Download the `better-qrcodes-<version>-pcm.zip` release asset. In KiCad, open **Plugin and Content Manager → Install from File**, select the ZIP, and restart the PCB Editor. Do not extract the archive first.

For a manual installation, copy the `better_qr_codes` directory into your KiCad 10 user plugin directory:

| Platform | Directory |
| --- | --- |
| Windows | `%USERPROFILE%\Documents\KiCad\10.0\scripting\plugins` |
| Linux | `~/.local/share/kicad/10.0/scripting/plugins` |
| macOS | `~/Documents/KiCad/10.0/scripting/plugins` |

The Better QR Codes button appears on the PCB Editor toolbar. Double-click an existing code, or select it and open the plugin, to edit and regenerate it. Move, rotate and flip it with KiCad's normal tools or the Properties panel. Change its size in the plugin dialog.

## Development

Run the tests with normal Python:

```text
python -m unittest discover -s tests
```

Run them with KiCad's Python as well to exercise the board-geometry tests. Build an installable PCM archive with:

```text
python scripts/build_release.py
```

Release artifacts are written to `dist/`. See [RELEASING.md](RELEASING.md) for the release and official KiCad repository workflow, [FEATURES.md](FEATURES.md) for the backlog, and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled component and icon attribution.

The Better QR Codes source code is released under the [MIT License](LICENSE). Bundled component licenses and icon attribution are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
