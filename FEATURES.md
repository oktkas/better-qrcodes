# Feature list

Planned features for future implementation. This is a backlog, not a release commitment.

## 1. Adjustable corner radius

- Set module corners anywhere from square to fully rounded.
- Round exposed corners while keeping adjacent modules connected.
- Configure finder-pattern styling separately from data modules.

## 2. Module thickness and gap control

- Adjust the size of each dark module within its grid cell.
- Support square and circular modules.
- Enforce conservative limits and warn about fragile or unscannable geometry.

## 3. Knockout

- Render the QR code as a negative cutout from a solid background.
- Select the knockout margin from a menu:
  - **Standard — 4 modules (default)**
  - **Thin — 2 modules**
  - **Custom** — reveals an input for the margin in modules
- Apply the selected margin consistently on every side.
- Show the knockout area in the live preview.
- Warn when a custom margin is too small for reliable scanning or fabrication.

## 4. Independent finder-pattern styling

- Configure the three finder patterns independently from the data modules.
- Offer square, rounded-square, and circular outer and inner shapes.
- Keep standard finder patterns as the safe default.

## 5. Physical size and quiet zone

- Set the overall size in millimetres or set an exact module size.
- Display the resulting QR version, module count, module size, and total footprint.
- Use a four-module quiet zone by default, with an expert override and warning for smaller values.
- Always show the quiet-zone boundary in the preview, using a dashed outline that is not included in the generated board geometry.
- Clearly distinguish the quiet zone from the optional knockout margin.

## 6. Error correction

- Support automatic selection and levels L, M, Q, and H.
- Explain the size and reliability tradeoff for each level.
- Recommend stronger error correction when styling removes or reduces QR geometry.
- Increase error correction automatically when possible without increasing the QR version.

## 7. PCB layer and polarity

- Support suitable silkscreen, solder-mask, copper, and user layers.
- Generate positive or negative geometry.
- Provide practical presets for common PCB material and layer combinations.
- Make the physical meaning of foreground and background clear in the preview.

## 8. Fabrication-aware warnings

- Check minimum module width, gap width, and feature size.
- Allow manufacturing constraints to be configured.
- Warn when rounding, thinning, knockout margins, or scaling violate those constraints.
- Distinguish fabrication warnings from QR-structure errors.

## 9. Live preview and validation

- Preview the actual geometry that will be placed in KiCad.
- Include layer, polarity, knockout, and quiet-zone visualization.
- Attempt to decode the final generated geometry before insertion.
- Report a clear status: valid, risky, or undecodable.
- Check normal and inverted rendering when relevant.

## 10. QR version control

- Automatically select the smallest suitable QR version by default.
- Allow advanced users to choose a specific version.
- Report when the payload cannot fit the selected version.
- Recalculate physical dimensions and validation whenever the version changes.

## 11. Presets

- Save and reuse complete style and fabrication presets.
- Include module shape, corner radius, thickness, finder style, error correction, layer, polarity, quiet zone, knockout, and sizing.
- Ship only a small set of useful PCB-oriented defaults.
- Keep payload data separate from reusable appearance presets.

## 12. Batch generation

- Generate multiple codes from a list of payloads or serial values.
- Support numbered sequences and project or board variables.
- Apply one validated preset consistently across a batch.
- Preview and validate every generated code before placement.
- Make unique values and failures easy to identify before committing the batch to the board.

