# Ocean Proto — Design Tokens
## Inherits: Esoteria Style Guide v1.0

INSTANCE: Ocean Proto
ACCENT_COLOR: #C0392B
ACCENT_HOVER: #A93226
LOGO_TEXT: ZOHAR // OCEAN PROTO
DEPLOYED_AT: localhost:8080
LAST_UPDATED: 2026-04-25

## Overrides

The following overrides are approved for the geospatial
dashboard context (map-based UI):

- Data visualization colors on map markers and layer dots
  are semantic (encode data category) and do not follow
  the accent-only rule. These include:
  - Vessel markers: #ff8844
  - Megafauna markers: #44bbff
  - Oil platform markers: #ff5577
  - OSV markers: #ff66cc
  - AIS gap markers: #ffdd44
  - Risk heatmap: Leaflet color scale (YlOrRd)

- Gap event markers use a CSS keyframe animation
  (gapPulse) as a functional indicator of active
  transponder blackout zones. This is not decorative;
  it communicates alert state to the operator.

- Layer dot indicators use border-radius: 50% as
  they are functional color swatches, not UI containers.

- Stat card value colors match their corresponding
  layer colors for cross-referencing.

All other design tokens (background, surface, border,
text hierarchy, font, spacing, buttons, panels) follow
the Esoteria Style Guide v1.0 without exception.

## Approved By
Douglas Galloway — 2026-04-25
