# ultraETH — updates

Changelog for `ultraETH.ipynb`.

## Structure

ultraETH is a premium-financed leveraged ETH call structure — three equal ⅓-of-capital
slices, each sized so its Black-Scholes premium consumes ⅓ of the deployed capital:

| Slice | Tenor | Legs |
|---|---|---|
| 1 | 15m | long 25% OTM call, short 0.66× 125% OTM call (partial collar) |
| 2 | 18m | long 25% OTM call, short 0.66× 125% OTM call (partial collar) |
| 3 | 24m | long 25% OTM + 75% OTM + 125% OTM calls |

Assumptions: spot = 2500, vol = 70%, r = 0. Fees: 10% upfront on deposited capital,
15% performance fee on profit above the deposit (high-water mark).

## Notebook layout

- **Inputs** — spot / vol widgets (`inputs` dict).
- **# Payoff** — terminal (expiry) payoff, built in stages:
  1. Whole product, net of premium.
  2. + 10% upfront fee.
  3. + 15% performance fee.
  4. ultraETH final payoff (as offered) vs buy & hold ETH only.
- **# Instantaneous value** — table of position value today if spot moves immediately
  (full tenor remaining, time value intact), net of upfront fee.

## Key figures (70% vol)

Final structure (10% upfront + 15% perf fee):

- Breakeven: **+51.5%** above spot (S_T ≈ $3,788)
- Beats buy & hold ETH: **+74.7%** (S_T ≈ $4,368)
- Immediate delta at spot: **~2.07×**

Expiry payoff leverage:

| Underlying gain | Leverage |
|---|---|
| +25% to +51% | 3.78× |
| +51% to +75% | 3.22× |
| +75% to +125% | 3.58× |
| +125% and above | 2.07× |

Instantaneous value if spot moves immediately (% of deposit, net of upfront fee):

| Immediate move | ultraETH | Hold ETH |
|---|---|---|
| +0% | 90% | 100% |
| +25% | 140% | 125% |
| +50% | 195% | 150% |
| +100% | 313% | 200% |
| +125% | 374% | 225% |

## Change log

- Terminal payoff reworked from raw option legs to the whole net-of-premium structure.
- Axes switched to % underlying gain (x) and % USD return (y).
- Added Black-Scholes premium pricing; sized each slice to ⅓ of capital.
- Added breakeven and "beats spot" markers.
- Added 10% upfront-fee and 15% performance-fee forks.
- Vol assumption set to 70% (reproduces the ~51% breakeven / ~4× leverage target).
- Added instantaneous-value section (delta view), rendered as a table.

## Notes / open items

- r = 0, flat vol (no skew), no ETH drift. Real desk figures may differ — a vol skew or
  drift raises far-region leverage.
- "2× immediate exposure" is approximate: at entry the position is worth 90% of deposit
  (the upfront fee), and the multiple grows with the move (positive gamma).
