# Color

- Palette: neutral base + one accent hue; add status hues (error, warning, success) only as semantic tokens.
- IF brand colors exist -> derive tokens only from them; ELSE start monochromatic (tints/shades of one hue).
- IF more hues are needed -> analogous for low contrast, complementary for high; never 4+ hue harmonies.
- Distribute area 60% dominant neutral / 30% secondary neutral / 10% accent.
- Accent marks the single most important element (primary CTA, key interactive); use the same action color for every CTA on every screen.
- One meaning per color across the UI; red/warm-bright tokens only for errors/warnings.
- Build hierarchy from value and saturation steps, not hue: high saturation for top priority, desaturated for lesser.
- Max 3 contrast tiers; header, subheader and body each get a distinct tier.
- Moderate saturation and brightness; no neon, no saturated hue pairs with low luminance separation.
- Secondary buttons: no light-grey fills (read as disabled); use outline or tinted fill.
- Balance icon weight with label color darkness.
- Define light and dark schemes as tokens; tune dark mode with APCA Lc, not WCAG ratio.
- Cap Lc at 90 for text >36px bold and large color fields.
- Text on images/video: add scrim or solid backing.
- Keep borders, icons, fields and separations intact under forced-colors and inverted modes; avoid background-only boundaries.
- Check palette under color-blindness simulation; no untested cultural/emotional color semantics.
- Check imagery color dominance before placement.
