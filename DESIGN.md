# Design

## Theme

A code instrument for working developers — near-black canvas, mineral-teal primary, copper accent. Restrained color strategy: neutrals carry the surface, primary carries action/selection, three agent voice colors (Host teal, Saboteur rust, Evaluator jade) appear only where agent identity carries information. Dark by necessity: the editor is the product, ambient focus, dim office. Calm. Considered. Crafted.

## Color (OKLCH)

| Role | Token | Value |
|---|---|---|
| Background | `--color-bg` | `oklch(0.135 0.000 0)` — pure near-black, chroma 0 |
| Surface | `--color-surface` | `oklch(0.170 0.003 220)` |
| Surface 2 | `--color-surface-2` | `oklch(0.205 0.004 220)` |
| Hairline | `--color-hair` | `oklch(0.270 0.004 220)` |
| Ink (body) | `--color-ink` | `oklch(0.935 0.004 220)` — ≥7:1 |
| Ink soft | `--color-ink-soft` | `oklch(0.720 0.006 220)` — ≥4.5:1 |
| Muted | `--color-muted` | `oklch(0.580 0.008 220)` — ≥3.5:1 |
| Primary | `--color-primary` | `oklch(0.620 0.110 195)` — mineral teal |
| Accent | `--color-accent` | `oklch(0.760 0.130 70)` — copper |
| Host | `--color-host` | `oklch(0.700 0.120 195)` |
| Saboteur | `--color-saboteur` | `oklch(0.640 0.135 35)` |
| Evaluator | `--color-evaluator` | `oklch(0.720 0.110 158)` |
| Student | `--color-student` | `oklch(0.760 0.090 250)` |
| System | `--color-system` | `oklch(0.740 0.110 85)` |

Text on saturated fills: white/near-white (`--color-bg`), per Helmholtz–Kohlrausch.

## Typography

- **Inter** for UI: 400/500/600/700. Fixed rem scale (product register). `letter-spacing: -0.006em` body, `-0.02em` headings.
- **JetBrains Mono** for code-adjacent labels, trace, session IDs, tabular figures (`tnum`).
- Body 14px / 1.55. Headings fixed (not fluid): h1 ~2.5rem on home, smaller on session surfaces.
- No display font in UI labels. One family carries the hierarchy.

## Layout

- 1200px max content width. Session grid: `minmax(0,1fr) / 380px` — editor primary, side rail secondary.
- Hairline borders (1px) over cards-as-default. Challenge renders as a typographic block with a primary-tinted left rule, not a boxed card.
- Status strip: wordmark → loop strip → session metadata → connection dot.

## Components

- **Segmented control**: radio-group, primary fill on active, hairline container, 5px radius.
- **Buttons**: primary (mineral teal, white text, 1px shadow lift), secondary (hairline border, surface-2 hover).
- **Panels**: hairline-bordered, uppercase muted title bar, scrollable body.
- **Chat**: role dot + colored label + tabular timestamp; system messages get a system-tinted border + wash.
- **Trace**: monospace log, expandable rows, status glyphs (✓/✗) in semantic colors.
- **Score**: tabular total with semantic color, four breakdown bars.

## Motion

- 140–320ms, ease-out (`cubic-bezier(0.16,1,0.3,1)`). State only: reveals, bar fills, button press.
- No orchestrated page-load. `prefers-reduced-motion` → instant crossfade, no transform.

## Monaco

Custom `agentx` theme: surface-matched background, mineral-teal keywords, copper strings/numbers, jade types, faint gutter numbers.
