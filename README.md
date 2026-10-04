# Better QR Codes

Better QR Codes is a KiCad plugin for creating more flexible, visually refined QR codes on PCB designs.

Planned improvements over KiCad's native QR-code generator include:

- Rounded corners
- Thinner graphic knockouts
- Practical styling options that remain reliably scannable

These features may go beyond the original QR-code specification, but are widely supported by modern scanners.

## Current functionality

- Regular QR Code Model 2 symbols
- Content, error-correction, layer, and physical-size controls
- Active PCB layers, shown with the current KiCad theme colors
- Live preview using the selected layer color and PCB editor background
- Toolbar action in KiCad's PCB Editor
- Plugin-owned grouped artwork that remains movable and scalable with KiCad tools
- Re-editing by double-clicking a generated group or opening the plugin with it selected

## Install for development

Better QR Codes currently targets KiCad 10.

Copy the `better_qr_codes` directory into your KiCad 10 Action Plugins directory, then restart the PCB Editor. On Windows, the default destination is:

```text
%APPDATA%\kicad\10.0\scripting\plugins\better_qr_codes
```

The Better QR Codes button will appear on the PCB Editor toolbar. Double-click an existing Better QR Codes group, or select it and open the plugin, to edit and regenerate it.

Run the model tests with:

```text
python -m unittest discover -s tests
```

See [FEATURES.md](FEATURES.md) for the planned feature backlog.
