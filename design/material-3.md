# Material 3 in PFI

One Material 3 look for the Windows app, the phone app and the website.

## Tokens

- **Seed:** `#2F6FE4` (PFI blue). **Scheme:** `SchemeFidelity`, standard
  contrast, from `@material/material-color-utilities` 0.4.0.
- **Source of truth:** `design/m3-tokens.json`. Regenerate everything with:

  ```
  cd frontend && npm ci && cd ..
  node --import ./scripts/m3/resolve-js.mjs scripts/m3/gen-tokens.mjs
  ```

  This writes `frontend/app/m3-tokens.css`, `frontend/lib/m3-tokens.json`,
  `docs/m3-tokens.css` and `mobile/lib/ui/m3_tokens.dart`.
- **Money colours:** green `#1E8E3E` (in), red `#D93025` (out) and amber
  `#E8A33D` (warning). They are harmonized toward the seed, with the
  `positive`, `negative` and `warning` roles plus their containers.
- **Other accents:** a different accent chosen in Settings becomes a new
  seed. On the PC it is applied at run time by `frontend/lib/m3.ts`, which
  uses the same algorithm. On the phone it goes through
  `ColorScheme.fromSeed(dynamicSchemeVariant: fidelity)`.
- **Icons:** Material Symbols Rounded, subset to the glyphs listed in
  `frontend/components/icons.ts`. After adding an icon there, run
  `python scripts/m3/subset-icons.py`. The subset is 15 KB; the full font
  is about 5 MB.
- **Type:** Roboto Flex, with Noto Sans Arabic for Arabic. The website
  self-hosts Roboto Flex in `docs/fonts/`.

| Shape token | Value | Used for |
|---|---|---|
| extra-small | 4px | text fields, settings rows inside a group |
| small | 8px | chips, tags, status pills |
| medium | 12px | cards, menus, list rows |
| large | 16px | FAB, settings groups, side panels |
| extra-large | 28px | dialogs, content pane, hero |
| full | 999px | buttons, navigation indicator |

## Handoff

- **Intent:** a calm, readable finance tool. There is one expressive moment
  per screen, the net-worth hero on Home. Dense data stays quiet.
- **Layout:**
  - A navigation drawer (280px) holds 15 destinations in 4 groups, with
    Settings last.
  - Below 1000px wide it becomes a navigation rail (88px) with the same
    destinations in the same order.
  - Content sits in a `surface` pane with 28px corners on a
    `surface-container` window background.
  - The Windows shell hides its native NavigationView pane
    (`IsPaneVisible="False"`). The items stay for route sync.
- **Colour roles:**
  - Cards use `surface-container-low`.
  - Selection uses `secondary-container`.
  - The primary action (the FAB) uses `primary-container`.
  - Status uses the `positive` / `negative` / `warning` containers with
    their on-container text.
- **Component map:**
  - The extended FAB "Add transaction" (Ctrl+N) is the single primary
    action. It replaced the duplicate primary button on Transactions and
    the hero quick actions, which repeated navigation.
  - Period switches use tabs.
  - Budget filters use filter chips.
  - Settings use a segmented list.
  - Fluent UI v9 controls are themed so that their tokens map to M3 roles.
- **States:**
  - Hover and press use state layers (8% / 10% of the "on" colour).
  - Focus shows a 3px `secondary` outline.
  - The selected destination shows a filled icon on the indicator.
- **Accessibility:**
  - Text pairs are at least 4.5:1 in light and dark.
  - Nav targets are 56px tall.
  - Status is never shown by colour alone: there are labels such as
    "Overspent" and "At risk".
  - RTL is mirrored through logical properties.
- **Motion:**
  - Standard easing at 150ms for state changes.
  - An emphasized-decelerate entrance on the hero number.
  - Everything is off under `prefers-reduced-motion`.
- **Charts:** the Okabe–Ito palette (colour-blind safe) is kept on purpose.
  Material 3 does not define a data-visualisation palette.

## Self-audit (v0.9)

| Area | Result |
|---|---|
| Task clarity | One FAB for the main task. Destinations and actions are no longer mixed (hero quick links removed). |
| Hierarchy | headline-medium page titles, title-medium card titles, display-size hero, no all-caps labels. |
| Component semantics | Drawer and rail for destinations, tabs for peer views, filter chips for filters, FAB for the primary action. |
| Token discipline | All colours come from roles. The older CSS names are aliases of roles, and the shape scale has 6 steps. |
| Adaptive | Drawer to rail at 1000px, same order. Panes reflow at 1100px and 900px. |
| States | Hover, pressed, focus and selected states use M3 state layers and indicators. |
| Accessibility | Contrast was checked from the tokens. Reduced motion is supported. Icons are aria-hidden next to visible labels. |
| Expressive restraint | One hero per screen. No gradients, no shadows on cards, no pills on chips or fields. |

**Known gaps:**

- Fluent dropdowns and date fields keep Fluent's internal layout, with M3
  colours and shapes.
- The Windows title bar is still the native Mica bar.
