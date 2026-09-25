# CurlCommander — Design system (web GUI + TUI)

Locked with the Repaint pipeline. Register: **product-app** (dev/security tool,
data-dense + command-driven). Anchor: **dev-tooling design systems** — Carbon
(enterprise density, color-contrast elevation), Primer/VS Code (editor chrome,
one interactive accent), Linear-calm restraint. Mode: production / **overhaul**.

Not a SaaS dashboard, not marketing. An editor-style working tool a pentester /
AppSec / API engineer uses for hours. Density and typographic hierarchy over
decoration; color carries **state and risk**, never ornament.

## Hard constraint: offline-first
The tool runs in isolated/air-gapped labs. **No web-font CDN.** UI uses a system
sans stack; all technical data uses a monospace stack. Identity comes from
density + mono-forward hierarchy, not a downloaded typeface.

## Color tokens (dark-first, warm-tinted neutrals; elevation by luminance, no shadow)
| Token | Value | Use |
|---|---|---|
| `--bg` | #0d0f13 | app ground |
| `--surface` | #14181e | panels, sidebar |
| `--surface-2` | #1a1f26 | inputs, table header, rows |
| `--surface-3` | #232a33 | hover / selected |
| `--border` | #2a313b | hairlines |
| `--border-strong` | #39424e | region dividers |
| `--fg` | #e7ebf0 | primary text (not #fff) |
| `--fg-muted` | #99a3b0 | secondary |
| `--fg-faint` | #67707c | tertiary / disabled |
| `--accent` | #3d7fd6 | interactive ONLY: send, selection, focus, active tab |
| `--accent-hover` | #4d8fe6 | interactive hover |
| `--accent-soft` | rgba(61,127,214,.16) | selection tint |
| `--focus` | #6aa5ea | focus-visible ring (≥3:1) |

### Semantic — HTTP status (solid, no gradient)
2xx `--ok` #46b17e · 3xx `--warn` #d39a3c · 4xx `--err` #e5544b · 5xx `--err` bold.

### Semantic — severity
critical `--crit` #db3b63 · high `--err` #e5544b · medium `--warn` #d39a3c ·
low `--info` #4d94c9 · info `--fg-muted`.

The interactive accent (blue) is a distinct hue from every status/severity color,
so "blue" never means a result — only an action.

## Type
- `--ui`: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` — labels, nav, buttons, headings.
- `--mono`: `ui-monospace, "JetBrains Mono", "Cascadia Code", "SF Mono", "Menlo", Consolas, monospace` — URLs, methods, status, headers, bodies, curl, all table data.
- Sizes: 11 (meta/tags), 12 (dense UI), 13 (body/data), 15 (view title). Hierarchy by size+weight+color, not containers.

## Spacing — 4px grid
4 / 8 / 12 / 16 / 24. Panel padding 8–10. Table cell 4–10. No 32+ gaps inside the app.

## Radius — minimal
`--r-sm` 3px (inputs, buttons, tags) · `--r-md` 5px (panels). Never 8–12px rounded cards.

## Elevation
None via shadow. Surfaces step by luminance (Carbon). Borders separate regions.

## Motion
120ms (state), 180ms (panel). `ease`. No bounce. Honor `prefers-reduced-motion`.

## Interaction states (all 8)
default / hover (surface-3 or accent-hover) / focus-visible (2px `--focus` ring) /
active (pressed inset) / selected (accent-soft bg + accent left-rule) /
loading (inline "…" + aria-busy, never a blocking full-page spinner) /
empty (specific, points somewhere) / disabled (fg-faint, no pointer).

## Accessibility
Landmarks (`<nav>`/`<main>`/status `<footer>`), one `<h1>`, real `<label>` per input
(no placeholder-as-label), `aria-live="polite"` status region, visible focus ring,
`lang` on `<html>`. Product-app → no SEO head.

## Slop removed (name-swap test must fail)
neon SaaS blue → restrained accent · floating rounded cards → hairline panes ·
big rounded buttons → compact toolbar · `⌘` decorative mark → inline SVG wordmark ·
placeholder-as-label → real labels · added persistent status bar (context) ·
mono-forward data. No gradients, no glow, no glassmorphism, no shadow-elevation,
no hacker-neon cliché.
