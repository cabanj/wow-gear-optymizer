# UX Audit — WoW Gear Upgrade Analyzer
Date: 2026-09-04 · Scope: `/characters` + `/reports/{id}` (reduced: logged-out surface + mock renders, auth blocks full crawl)
Method: skill `ux-audit` — pa11y WCAG2AA, headless Chromium screenshots @1280/768/390, vision review, perf notes.

## Accessibility (pa11y, WCAG2AA)
- `report_detail.html`: **0 issues** ✅
- `characters.html`: **4 issues** ❌
  - 2× `add-realm` / `add-name` inputs have no `<label>` (WCAG F68)
  - 2× `aria-label`/`title`-only naming on icon buttons (Name rule)

## Visual audit — characters @1280
1. **Dead space**: content fills left ~45% viewport, right half empty. Fix: `max-width: 1100px; margin: 0 auto` on `.layout` or center the two-column grid.
2. **Wide column gap** (~80–100px) disconnects sidebar from gear panel. Fix: gap 24–32px + shared card background.
3. **Gear rows**: right values (slot label + ilvl) don't form a strict column; baseline of label vs number is off. Fix: fixed-width right column, `align-items: baseline`.
4. **Gray micro-text** (`#9ca3af` @12–13px: realm lines, timestamps, gems) sits near AA boundary — bump to `#b6bcc8` or 13px.
5. **Selection linkage**: selected card has blue border but nothing ties it to the right panel. Fix: matching accent bar or "Showing: Calipse" caption above gear grid.

## Visual audit — report @1280
1. **Dangling `±`**: `+0.13% ±` shows the symbol with the value hidden in a `title` tooltip (touch users never see it). Fix: render `±0.03%` inline or drop the symbol and keep one "within error" badge.
2. **`Group by boss: off` pill reads as disabled**, not a toggle. Fix: switch-style control or label `Grouped: off`.
3. **Subtitle metadata** (`raid:1320;season:18`, build strings) is one dense line. Fix: `·`-separated, hide build numbers behind `<details>`.
4. **Bars have no scale/legend** — relative widths only. Fix: `title` attr or tiny axis note ("bar ∝ DPS gain vs best").
5. Chart renders X labels fine (earlier "missing axis" was screenshot crop, not a bug).

## Mobile @390
- `#1` summary card: long item names nearly touch card edges — add `overflow-wrap` + min padding.
- Filter row 1 (All/Raid/Mythic+/Group) overflows → allow `flex-wrap`.
- Snapshot line: unbroken version strings (`12.1.0.69587`) risk horizontal scroll → `overflow-wrap: anywhere`.
- Checkboxes and `+` button are ~16–20px targets (min 44px). Fix: larger hit area via padding.
- Header crowds at 390px — allow battletag to wrap below title.

## Performance
- No JS framework ✅; one 5KB CSS ✅; Chart.js via CDN (defer, only on detail page) ✅
- Gear icons hot-linked from `render.worldofwarcraft.com` (no `loading="lazy"`, no size attrs) — add `loading="lazy" width="56" height="56"` to kill layout shift.

## Priority fix list
| # | Fix | Effort |
|---|-----|--------|
| 1 | Labels for add-realm/add-name inputs (a11y blocker) | S |
| 2 | `±` value inline instead of title-only | S |
| 3 | Center layout / max-width + narrower column gap | S |
| 4 | Filter wrap + snapshot overflow-wrap (mobile) | S |
| 5 | Gear lazy icons with dimensions (CLS) | S |
| 6 | Toggle restyle for group-by; metadata `<details>` | M |
| 7 | 44px tap targets on checkboxes/buttons | M |
