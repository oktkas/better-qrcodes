# Changelog

## [Unreleased]

- Codes are now board-only footprints, so position, orientation and side show in KiCad's Properties panel and work with R, Move Exactly and Flip at any angle.
- Back-side layers place the code flipped and upright as seen from below (orientation 180°); switching sides in the dialog converts the orientation like KiCad's Flip.
- Codes made by 0.1.x are converted to footprints the first time they are edited.

## [0.1.1] - 2026-10-25

- Move the project to GitHub; the PCM identifier is now `com.github.oktkas.better-qrcodes`.
- Refresh the toolbar and package icons.
- Mark the release stable so it is offered by default in the Plugin and Content Manager.

## [0.1.0] - 2026-10-04

Initial testing release for KiCad 10.

- Create and re-edit regular QR Code Model 2 artwork.
- Select content, error correction, board layer, and physical size.
- Round data modules and complete finder-pattern geometry independently.
- Add module-based knockout backgrounds with independent corner rounding.
- Preview the final geometry and four-module quiet zone.
