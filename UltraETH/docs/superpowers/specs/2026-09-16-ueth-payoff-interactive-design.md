# uETH Payoff Interactive — Design

## Purpose

A retail-facing, self-contained web interactive (single HTML artifact) that lets a
user explore the payoff of the "Ultra ETH" (uETH) structured product: two sliders
(time since entry, volatility) drive a live-recomputed chart of uETH value vs. ETH
price. Marketing narrative/copy from the one-pager is reproduced; the option-leg
mechanics that back the structure are not shown to the retail user — the pricing
engine uses them internally only.

## Ground truth

The actual trade (7 option legs, real strikes/quantities/premiums) is the pricing
source. Displayed stats (breakeven, leverage) are computed live from this engine,
not hardcoded from the marketing one-pager, so they can't drift out of sync with
the real trade. If the engine's terminal-payoff curve materially disagrees with the
one-pager's stated breakeven (+60%) or leverage tiers, that discrepancy will be
surfaced to the user (Miffy) during validation, not silently reconciled.

## Trade data (internal only, not rendered to retail UI)

Derived constants:
- Entry spot `S0 = 2450` (strikes are exactly 1.25×, 1.75×, 2.25× of this)
- Entry date `2026-08-24` (24 months before the final 24-Aug-2028 expiry; consistent
  with the 15/18/24-month tenors landing on 24-Nov-27 / 24-Feb-28 / 24-Aug-28)

Legs (sign, qty, strike, expiry, entry premium per ETH):
| Sign | Qty | Strike | Expiry | Premium |
|---|---|---|---|---|
| Buy | 900 | 3062.5 | 2027-11-24 | 507.80 |
| Sell | 594 | 5512.5 | 2027-11-24 | 136.22 |
| Buy | 900 | 3062.5 | 2028-02-24 | 584.61 |
| Sell | 594 | 5512.5 | 2028-02-24 | 186.85 |
| Buy | 225 | 3062.5 | 2028-08-24 | 719.56 |
| Buy | 225 | 4287.5 | 2028-08-24 | 473.43 |
| Buy | 225 | 5512.5 | 2028-08-24 | 342.66 |

## Pricing engine

Fixed parameters: risk-free rate `r = 2%`. Vol is a slider input, not fixed.

`total_entry_cost` = Σ (sign × qty × entry_premium) over all 7 legs, computed once.

10% upfront fee on principal: normalization constant
`k = total_entry_cost / (0.9 × S0)`.
This makes uETH's t=0 fair value read as `0.9 × S0` (a visible −10% at entry) without
a separate fee line item anywhere else in the math.

For a given `(time_since_entry, vol, S)`:
- For each leg: if `entry_date + time_since_entry >= leg.expiry`, the leg has
  already cash-settled — value = intrinsic = `max(S - strike, 0)`, using `S` as the
  assumed constant price back through that expiry (no path-dependency is modeled;
  this simplifying assumption gets a one-line disclosure in the UI).
- Otherwise: value = Black-Scholes call price using `S`, `strike`, remaining time to
  that leg's own expiry, `vol`, `r`.
- `structure_value(S, t)` = Σ (sign × qty × leg_value)
- `uETH_value(S, t) = structure_value(S, t) / k`

## UI

Single self-contained HTML/JS Claude Artifact. No external libraries (CSP blocks
CDNs) — hand-rolled inline SVG chart per the dataviz skill.

Visual style, borrowed from app.ethstrat.xyz: soft lavender/off-white background,
white rounded cards with soft shadows, bold rounded sans-serif headings, pink/
magenta accent for key numbers and highlights, a 2-column stat-tile grid for key
metrics, gradient banner styling for the risk/disclosure section. Theme-aware
(light and dark via `prefers-color-scheme` / `data-theme`), responsive, no
horizontal page scroll.

Sections, top to bottom:
1. **Hero/narrative** — titular question framing, "no liquidations for 2 years,
   no funding rates," immediate-leverage teaser. Adapted from the one-pager copy,
   trimmed for retail (no mechanics jargon).
2. **Interactive chart** — x-axis: ETH price (0 to ~4×S0). y-axis: uETH value.
   Two sliders below/beside the chart:
   - Time since entry: 0 → 24 months, labeled with the actual calendar date
     (e.g. "Feb 2027") as it moves.
   - Volatility: 20%–150%, default 70%.
   Curve recomputes and redraws live on every slider input (no debounce needed at
   this scale). Single curve only — no spot/leverage reference overlay lines.
3. **Stat-tile row** — computed live from the current slider position: breakeven
   ETH price (where uETH_value(S, t) == S), and something like "at $X ETH your
   uETH is worth $Y (Z.zz× your deposit)" for a marker price. These are derived,
   not hardcoded, so they always match the curve shown.
4. **Risk section** — price risk (the titular bet) and counterparty risk, adapted
   from the one-pager. Include the 10% upfront fee as a plain disclosure line.

Not included: the Mechanics section, any leg/strike/quantity table, and the
one-pager's static instantaneous-delta table (superseded by the live stat tiles,
which cover the same idea — immediate leveraged exposure — without hardcoding
numbers that could drift from the real trade).

## Validation (before shipping)

1. At `t=0`, any vol: `uETH_value(S0, 0)` ≈ `0.9 × S0` (visible −10% entry fee).
2. At `t=24 months` (all legs expired), vol=70: compare the resulting terminal
   curve's breakeven and leverage bands against the one-pager's stated figures
   (breakeven ≈ +60% / ~3920, leverage tiers 3.78x/3.22x/3.58x/2.07x across the
   stated ETH-move bands). Report any material mismatch rather than silently
   adjusting one side to match the other.

## Out of scope

- Path-dependent settlement pricing for expired tranches (approximated as constant
  price back through expiry, disclosed).
- Risk-free rate as a slider (fixed at 2%, effect is small).
- Reference/comparison lines on the chart (spot ETH, naive 2x leverage).
- Early-exit / secondary liquidity pricing.
