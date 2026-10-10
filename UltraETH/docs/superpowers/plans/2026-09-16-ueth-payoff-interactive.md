# uETH Payoff Interactive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained, retail-facing HTML artifact that lets a user move two sliders (time since entry, volatility) and see a live-recomputed uETH payoff curve, priced off the real 7-leg option trade internally (never shown in the UI).

**Architecture:** A small pure-JS pricing engine (Black-Scholes + intrinsic-value roll-off over the 7 hardcoded legs) is built and unit-tested with Node's built-in test runner first, in isolation from any UI. Once validated (including a sanity script comparing the engine's terminal payoff against the one-pager's marketing claims), the validated logic is copied inline into a single self-contained HTML artifact alongside the retail UI (sliders, SVG chart, stat tiles, narrative/risk copy).

**Tech Stack:** Plain JavaScript (ES modules) for the engine, `node:test` + `node:assert/strict` for tests (Node v18+, no dependencies). Final deliverable is one HTML file with inline `<style>`/`<script>`, no external libraries (Claude Artifacts block CDN requests).

**Spec:** `docs/superpowers/specs/2026-09-16-ueth-payoff-interactive-design.md`

## Global Constraints

- No external libraries/CDNs in the final artifact — everything inline (per spec's Artifact requirement).
- Risk-free rate fixed at `r = 0.02` (2%), not a slider.
- 10% upfront fee folds into normalization constant `k = totalEntryCost / (0.9 * S0)` — no separate fee-subtraction step elsewhere.
- Retail UI must NOT show the 7 legs, strikes, or the Mechanics section — narrative + risk + fee disclosure + interactive chart only.
- Entry spot `S0 = 2450`, entry date `2026-08-24`, final expiry `2028-08-24` (731 days later).
- The 7 legs (sign, qty, strike, expiry, entry premium) are exactly as given in the spec — do not alter quantities/strikes/premiums.

---

## Task 1: Project scaffold + Black-Scholes core

**Files:**
- Create: `package.json`
- Create: `engine/blackScholes.mjs`
- Test: `engine/blackScholes.test.mjs`

**Interfaces:**
- Produces: `normCdf(x: number): number`, `blackScholesCall({ S, K, T, sigma, r }): number` — all four of `S, K, T, sigma, r` are plain numbers (`T` in years, `sigma` as a decimal e.g. `0.7` for 70%). Caller must ensure `T > 0`; this function does not special-case `T <= 0`.

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "ueth-payoff-interactive",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test engine/"
  }
}
```

- [ ] **Step 2: Write the failing test**

Create `engine/blackScholes.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { normCdf, blackScholesCall } from './blackScholes.mjs';

test('normCdf(0) is 0.5', () => {
  assert.ok(Math.abs(normCdf(0) - 0.5) < 1e-6);
});

test('normCdf is monotonically increasing', () => {
  assert.ok(normCdf(-1) < normCdf(0));
  assert.ok(normCdf(0) < normCdf(1));
});

test('blackScholesCall matches known textbook value (S=100,K=100,T=1,sigma=0.2,r=0.05)', () => {
  const price = blackScholesCall({ S: 100, K: 100, T: 1, sigma: 0.2, r: 0.05 });
  assert.ok(Math.abs(price - 10.4506) < 0.01, `got ${price}`);
});

test('deep in-the-money call approaches intrinsic value as T shrinks', () => {
  const price = blackScholesCall({ S: 200, K: 100, T: 0.001, sigma: 0.2, r: 0.05 });
  assert.ok(Math.abs(price - 100) < 1, `got ${price}`);
});

test('deep out-of-the-money call approaches zero as T shrinks', () => {
  const price = blackScholesCall({ S: 50, K: 100, T: 0.001, sigma: 0.2, r: 0.05 });
  assert.ok(price < 0.5, `got ${price}`);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `node --test engine/blackScholes.test.mjs`
Expected: FAIL — `engine/blackScholes.mjs` does not exist yet (module not found).

- [ ] **Step 4: Write the implementation**

Create `engine/blackScholes.mjs`:

```js
function erf(x) {
  const sign = x < 0 ? -1 : 1;
  x = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * x);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return sign * y;
}

export function normCdf(x) {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

export function blackScholesCall({ S, K, T, sigma, r }) {
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `node --test engine/blackScholes.test.mjs`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add package.json engine/blackScholes.mjs engine/blackScholes.test.mjs
git commit -m "Add Black-Scholes call pricing core with tests"
```

---

## Task 2: Trade data, date math, entry cost & normalization constant

**Files:**
- Create: `engine/trade.mjs`
- Test: `engine/trade.test.mjs`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `S0 = 2450`, `ENTRY_DATE = '2026-08-24'`, `FINAL_EXPIRY = '2028-08-24'`, `RISK_FREE_RATE = 0.02`, `LEGS` (array of `{ dir, qty, strike, expiry, premium }`), `daysBetween(isoStart, isoEnd): number`, `totalDaysToFinalExpiry(): number`, `computeTotalEntryCost(): number`, `computeK(): number`. Later tasks import `LEGS`, `S0`, `ENTRY_DATE`, `RISK_FREE_RATE`, `daysBetween`, `computeK`, `totalDaysToFinalExpiry` from this file.

- [ ] **Step 1: Write the failing test**

Create `engine/trade.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  S0, LEGS, daysBetween, totalDaysToFinalExpiry,
  computeTotalEntryCost, computeK,
} from './trade.mjs';

test('daysBetween handles same-day, one-day, and leap-year spans', () => {
  assert.equal(daysBetween('2026-08-24', '2026-08-24'), 0);
  assert.equal(daysBetween('2026-08-24', '2026-08-25'), 1);
  assert.equal(daysBetween('2026-08-24', '2028-08-24'), 731);
});

test('totalDaysToFinalExpiry matches entry-to-final-expiry span', () => {
  assert.equal(totalDaysToFinalExpiry(), 731);
});

test('LEGS has exactly 7 legs matching the real trade', () => {
  assert.equal(LEGS.length, 7);
  const nov27 = LEGS.filter((l) => l.expiry === '2027-11-24');
  const feb28 = LEGS.filter((l) => l.expiry === '2028-02-24');
  const aug28 = LEGS.filter((l) => l.expiry === '2028-08-24');
  assert.equal(nov27.length, 2);
  assert.equal(feb28.length, 2);
  assert.equal(aug28.length, 3);
});

test('computeTotalEntryCost matches the real trade premiums', () => {
  const cost = computeTotalEntryCost();
  assert.ok(Math.abs(cost - 1136786.67) < 0.5, `got ${cost}`);
});

test('computeK derives from total entry cost and 10% fee on S0', () => {
  const k = computeK();
  const expected = computeTotalEntryCost() / (0.9 * S0);
  assert.ok(Math.abs(k - expected) < 1e-9);
  assert.ok(Math.abs(k - 515.5495) < 0.01, `got ${k}`);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/trade.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `engine/trade.mjs`:

```js
export const S0 = 2450;
export const ENTRY_DATE = '2026-08-24';
export const FINAL_EXPIRY = '2028-08-24';
export const RISK_FREE_RATE = 0.02;
export const FEE_RATE = 0.10;

export const LEGS = [
  { dir: 1, qty: 900, strike: 3062.5, expiry: '2027-11-24', premium: 507.80 },
  { dir: -1, qty: 594, strike: 5512.5, expiry: '2027-11-24', premium: 136.22 },
  { dir: 1, qty: 900, strike: 3062.5, expiry: '2028-02-24', premium: 584.61 },
  { dir: -1, qty: 594, strike: 5512.5, expiry: '2028-02-24', premium: 186.85 },
  { dir: 1, qty: 225, strike: 3062.5, expiry: '2028-08-24', premium: 719.56 },
  { dir: 1, qty: 225, strike: 4287.5, expiry: '2028-08-24', premium: 473.43 },
  { dir: 1, qty: 225, strike: 5512.5, expiry: '2028-08-24', premium: 342.66 },
];

function toUTCms(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d);
}

export function daysBetween(isoStart, isoEnd) {
  return Math.round((toUTCms(isoEnd) - toUTCms(isoStart)) / 86400000);
}

export function totalDaysToFinalExpiry() {
  return daysBetween(ENTRY_DATE, FINAL_EXPIRY);
}

export function computeTotalEntryCost() {
  return LEGS.reduce((sum, leg) => sum + leg.dir * leg.qty * leg.premium, 0);
}

export function computeK() {
  return computeTotalEntryCost() / ((1 - FEE_RATE) * S0);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/trade.test.mjs`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/trade.mjs engine/trade.test.mjs
git commit -m "Add trade leg data, date math, and fee-adjusted normalization constant"
```

---

## Task 3: Per-leg valuation with expiry roll-off

**Files:**
- Create: `engine/legValue.mjs`
- Test: `engine/legValue.test.mjs`

**Interfaces:**
- Consumes: `blackScholesCall` (Task 1); `daysBetween`, `RISK_FREE_RATE` (Task 2).
- Produces: `valueLeg(leg, { S, daysSinceEntry, sigma, entryDate }): number` — `daysSinceEntry` is an integer number of days since `entryDate` (both in the same units `daysBetween` uses). If the leg's own expiry has been reached or passed, returns intrinsic value `max(S - strike, 0)`. Otherwise returns a live Black-Scholes value using the leg's remaining time (in years, `remainingDays / 365`).

- [ ] **Step 1: Write the failing test**

Create `engine/legValue.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { valueLeg } from './legValue.mjs';
import { blackScholesCall } from './blackScholes.mjs';
import { LEGS, ENTRY_DATE, daysBetween, RISK_FREE_RATE } from './trade.mjs';

const nov27Leg = LEGS[0]; // buy 900x 3062.5C, expiry 2027-11-24

test('before expiry, valueLeg matches a direct Black-Scholes call', () => {
  const S = 2450;
  const sigma = 0.7;
  const daysSinceEntry = 0;
  const got = valueLeg(nov27Leg, { S, daysSinceEntry, sigma, entryDate: ENTRY_DATE });
  const daysToExpiry = daysBetween(ENTRY_DATE, nov27Leg.expiry);
  const expected = blackScholesCall({
    S, K: nov27Leg.strike, T: daysToExpiry / 365, sigma, r: RISK_FREE_RATE,
  });
  assert.ok(Math.abs(got - expected) < 1e-9);
});

test('exactly at its own expiry, valueLeg returns intrinsic value', () => {
  const daysToExpiry = daysBetween(ENTRY_DATE, nov27Leg.expiry);
  const got = valueLeg(nov27Leg, { S: 5000, daysSinceEntry: daysToExpiry, sigma: 0.7, entryDate: ENTRY_DATE });
  assert.ok(Math.abs(got - (5000 - nov27Leg.strike)) < 1e-9);
});

test('well past its own expiry, valueLeg still returns intrinsic value', () => {
  const daysToExpiry = daysBetween(ENTRY_DATE, nov27Leg.expiry);
  const got = valueLeg(nov27Leg, { S: 1000, daysSinceEntry: daysToExpiry + 200, sigma: 0.7, entryDate: ENTRY_DATE });
  assert.equal(got, 0); // 1000 < strike 3062.5, out of the money -> 0
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/legValue.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `engine/legValue.mjs`:

```js
import { blackScholesCall } from './blackScholes.mjs';
import { daysBetween, RISK_FREE_RATE } from './trade.mjs';

export function valueLeg(leg, { S, daysSinceEntry, sigma, entryDate }) {
  const daysToLegExpiry = daysBetween(entryDate, leg.expiry);
  if (daysSinceEntry >= daysToLegExpiry) {
    return Math.max(S - leg.strike, 0);
  }
  const remainingDays = daysToLegExpiry - daysSinceEntry;
  const T = remainingDays / 365;
  return blackScholesCall({ S, K: leg.strike, T, sigma, r: RISK_FREE_RATE });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/legValue.test.mjs`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/legValue.mjs engine/legValue.test.mjs
git commit -m "Add per-leg valuation with expiry roll-off to intrinsic value"
```

---

## Task 4: Portfolio aggregate (structure value & normalized uETH value)

**Files:**
- Create: `engine/payoff.mjs`
- Test: `engine/payoff.test.mjs`

**Interfaces:**
- Consumes: `valueLeg` (Task 3); `LEGS, ENTRY_DATE, computeK, S0` (Task 2).
- Produces: `structureValue({ S, daysSinceEntry, sigma }): number` (raw dollar value of the whole 7-leg structure, pre-normalization), `uEthValue({ S, daysSinceEntry, sigma }): number` (structure value divided by `computeK()`).

- [ ] **Step 1: Write the failing test**

Create `engine/payoff.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { structureValue, uEthValue } from './payoff.mjs';
import { computeK, S0, totalDaysToFinalExpiry } from './trade.mjs';

const MATURITY = totalDaysToFinalExpiry();

test('structureValue is 0 when ETH price is 0 at maturity', () => {
  assert.equal(structureValue({ S: 0, daysSinceEntry: MATURITY, sigma: 0.7 }), 0);
});

test('structureValue is 0 at maturity when ETH is exactly at the lowest strike', () => {
  assert.equal(structureValue({ S: 3062.5, daysSinceEntry: MATURITY, sigma: 0.7 }), 0);
});

test('structureValue at maturity, ETH exactly at the top strike (short legs contribute 0)', () => {
  const got = structureValue({ S: 5512.5, daysSinceEntry: MATURITY, sigma: 0.7 });
  assert.ok(Math.abs(got - 5236875) < 0.01, `got ${got}`);
});

test('structureValue at maturity, ETH at 6000 (exercises every leg)', () => {
  const got = structureValue({ S: 6000, daysSinceEntry: MATURITY, sigma: 0.7 });
  assert.ok(Math.abs(got - 5864287.5) < 0.01, `got ${got}`);
});

test('uEthValue is structureValue divided by computeK()', () => {
  const raw = structureValue({ S: 6000, daysSinceEntry: MATURITY, sigma: 0.7 });
  const got = uEthValue({ S: 6000, daysSinceEntry: MATURITY, sigma: 0.7 });
  assert.ok(Math.abs(got - raw / computeK()) < 1e-9);
});

test('at entry (t=0), uEthValue(S0) is within 20% of the fee-adjusted target (0.9*S0)', () => {
  // Real OTC premiums are not exactly reproduced by a flat-vol/flat-rate BS model
  // (desk skew, term structure, bid/ask), so this is a loose sanity bound, not an
  // exact-match assertion. See scripts/validate-against-onepager.mjs (Task 7) for
  // the precise, reported comparison.
  const got = uEthValue({ S: S0, daysSinceEntry: 0, sigma: 0.7 });
  const target = 0.9 * S0;
  assert.ok(Math.abs(got - target) / target < 0.2, `got ${got}, target ${target}`);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/payoff.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `engine/payoff.mjs`:

```js
import { LEGS, ENTRY_DATE, computeK } from './trade.mjs';
import { valueLeg } from './legValue.mjs';

export function structureValue({ S, daysSinceEntry, sigma }) {
  return LEGS.reduce((sum, leg) => {
    return sum + leg.dir * leg.qty * valueLeg(leg, { S, daysSinceEntry, sigma, entryDate: ENTRY_DATE });
  }, 0);
}

export function uEthValue({ S, daysSinceEntry, sigma }) {
  return structureValue({ S, daysSinceEntry, sigma }) / computeK();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/payoff.test.mjs`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/payoff.mjs engine/payoff.test.mjs
git commit -m "Add portfolio-level structure value and fee-normalized uETH value"
```

---

## Task 5: Root-finding, breakeven, and leverage stats

**Files:**
- Create: `engine/bisect.mjs`
- Create: `engine/stats.mjs`
- Test: `engine/bisect.test.mjs`
- Test: `engine/stats.test.mjs`

**Interfaces:**
- Consumes: `uEthValue` (Task 4); `S0` (Task 2).
- Produces: `bisectRoot(f, lo, hi, iterations = 60): number | null` (generic, no dependency on uETH specifics); `findBreakeven({ daysSinceEntry, sigma, lo = 1, hi = 20000 }): number | null`; `leverageMultiple({ S, daysSinceEntry, sigma }): number | null` (null when `S === S0`, since % return on ETH is undefined there).

- [ ] **Step 1: Write the failing test for `bisectRoot`**

Create `engine/bisect.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { bisectRoot } from './bisect.mjs';

test('finds the root of a simple linear function', () => {
  const root = bisectRoot((x) => x - 100, 0, 1000);
  assert.ok(Math.abs(root - 100) < 1e-6, `got ${root}`);
});

test('finds the positive root of x^2 - 4', () => {
  const root = bisectRoot((x) => x * x - 4, 0, 10);
  assert.ok(Math.abs(root - 2) < 1e-6, `got ${root}`);
});

test('returns null when the root is not bracketed', () => {
  const root = bisectRoot((x) => x * x + 1, -10, 10);
  assert.equal(root, null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/bisect.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `bisectRoot`**

Create `engine/bisect.mjs`:

```js
export function bisectRoot(f, lo, hi, iterations = 60) {
  let a = lo;
  let b = hi;
  let fa = f(a);
  const fb = f(b);
  if (fa === 0) return a;
  if (fb === 0) return b;
  if (Math.sign(fa) === Math.sign(fb)) return null;
  for (let i = 0; i < iterations; i++) {
    const mid = (a + b) / 2;
    const fm = f(mid);
    if (fm === 0) return mid;
    if (Math.sign(fm) === Math.sign(fa)) {
      a = mid;
      fa = fm;
    } else {
      b = mid;
    }
  }
  return (a + b) / 2;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/bisect.test.mjs`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing test for `stats.mjs`**

Create `engine/stats.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { findBreakeven, leverageMultiple } from './stats.mjs';
import { uEthValue } from './payoff.mjs';
import { S0, totalDaysToFinalExpiry } from './trade.mjs';

const MATURITY = totalDaysToFinalExpiry();

test('findBreakeven returns a price where uEthValue(S) approx equals S', () => {
  const breakeven = findBreakeven({ daysSinceEntry: MATURITY, sigma: 0.7 });
  assert.ok(breakeven !== null);
  const diff = uEthValue({ S: breakeven, daysSinceEntry: MATURITY, sigma: 0.7 }) - breakeven;
  assert.ok(Math.abs(diff) < 1, `breakeven=${breakeven}, diff=${diff}`);
});

test('leverageMultiple is null exactly at S0 (undefined % return denominator)', () => {
  assert.equal(leverageMultiple({ S: S0, daysSinceEntry: MATURITY, sigma: 0.7 }), null);
});

test('leverageMultiple is a finite number away from S0', () => {
  const lev = leverageMultiple({ S: S0 * 1.5, daysSinceEntry: MATURITY, sigma: 0.7 });
  assert.equal(typeof lev, 'number');
  assert.ok(Number.isFinite(lev));
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `node --test engine/stats.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 7: Write `stats.mjs`**

Create `engine/stats.mjs`:

```js
import { bisectRoot } from './bisect.mjs';
import { uEthValue } from './payoff.mjs';
import { S0 } from './trade.mjs';

export function findBreakeven({ daysSinceEntry, sigma, lo = 1, hi = 20000 }) {
  return bisectRoot(
    (S) => uEthValue({ S, daysSinceEntry, sigma }) - S,
    lo,
    hi,
  );
}

export function leverageMultiple({ S, daysSinceEntry, sigma }) {
  const spotReturn = S / S0 - 1;
  if (Math.abs(spotReturn) < 1e-9) return null;
  const uReturn = uEthValue({ S, daysSinceEntry, sigma }) / S0 - 1;
  return uReturn / spotReturn;
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `node --test engine/stats.test.mjs`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add engine/bisect.mjs engine/bisect.test.mjs engine/stats.mjs engine/stats.test.mjs
git commit -m "Add root-finding, breakeven, and leverage stat helpers"
```

---

## Task 6: Chart scale & path helpers

**Files:**
- Create: `engine/chartPath.mjs`
- Test: `engine/chartPath.test.mjs`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure generic math).
- Produces: `scaleLinear({ domain: [d0, d1], range: [r0, r1] }): (x: number) => number`; `buildPayoffPath({ points, xScale, yScale }): string` where `points` is `{ S: number, value: number }[]`, returning an SVG path `d` attribute string.

- [ ] **Step 1: Write the failing test**

Create `engine/chartPath.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { scaleLinear, buildPayoffPath } from './chartPath.mjs';

test('scaleLinear maps domain to range linearly', () => {
  const scale = scaleLinear({ domain: [0, 10], range: [0, 100] });
  assert.equal(scale(0), 0);
  assert.equal(scale(10), 100);
  assert.equal(scale(5), 50);
});

test('scaleLinear supports an inverted range (for SVG y-axes)', () => {
  const scale = scaleLinear({ domain: [0, 10], range: [100, 0] });
  assert.equal(scale(0), 100);
  assert.equal(scale(10), 0);
});

test('buildPayoffPath produces an SVG path string starting with M and using L for the rest', () => {
  const xScale = scaleLinear({ domain: [0, 10], range: [0, 10] });
  const yScale = scaleLinear({ domain: [0, 10], range: [0, 10] });
  const path = buildPayoffPath({
    points: [{ S: 0, value: 0 }, { S: 5, value: 5 }, { S: 10, value: 10 }],
    xScale,
    yScale,
  });
  assert.equal(path, 'M0.00,0.00 L5.00,5.00 L10.00,10.00');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chartPath.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `engine/chartPath.mjs`:

```js
export function scaleLinear({ domain, range }) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return (x) => r0 + ((x - d0) * (r1 - r0)) / (d1 - d0);
}

export function buildPayoffPath({ points, xScale, yScale }) {
  return points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${xScale(p.S).toFixed(2)},${yScale(p.value).toFixed(2)}`)
    .join(' ');
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chartPath.test.mjs`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/chartPath.mjs engine/chartPath.test.mjs
git commit -m "Add chart scale and SVG path helpers"
```

---

## Task 7: Validation script vs. the one-pager's marketing claims

**Files:**
- Create: `scripts/validate-against-onepager.mjs`

**Interfaces:**
- Consumes: `structureValue`, `uEthValue` (Task 4), `findBreakeven`, `leverageMultiple` (Task 5), `S0`, `totalDaysToFinalExpiry` (Task 2).
- Produces: console output only — this is a manual-inspection report script, not a pass/fail gate (per spec: report mismatches, don't paper over them).

- [ ] **Step 1: Write the script**

Create `scripts/validate-against-onepager.mjs`:

```js
import { findBreakeven, leverageMultiple } from '../engine/stats.mjs';
import { uEthValue } from '../engine/payoff.mjs';
import { S0, totalDaysToFinalExpiry } from '../engine/trade.mjs';

const MATURITY = totalDaysToFinalExpiry();
const VOL = 0.70;

console.log('--- t=0 sanity check (fee-adjusted entry value) ---');
const entryValue = uEthValue({ S: S0, daysSinceEntry: 0, sigma: VOL });
console.log(`uEthValue(S0, t=0, vol=70%) = ${entryValue.toFixed(2)} (target ~= ${(0.9 * S0).toFixed(2)})`);

console.log('\n--- Terminal payoff (t=24mo) vs. one-pager claims ---');
const breakeven = findBreakeven({ daysSinceEntry: MATURITY, sigma: VOL });
const breakevenPct = breakeven ? ((breakeven / S0 - 1) * 100).toFixed(1) : 'n/a';
console.log(`Computed breakeven: $${breakeven ? breakeven.toFixed(0) : 'n/a'} (${breakevenPct}% from entry)`);
console.log('One-pager claims: breakeven at +60% (~$3,920)');

console.log('\nLeverage by band (computed vs. one-pager):');
const bands = [
  { label: '+25% to +54%', move: 0.40, onePager: 3.78 },
  { label: '+54% to +75%', move: 0.65, onePager: 3.22 },
  { label: '+75% to +125%', move: 1.00, onePager: 3.58 },
  { label: '+125% and above', move: 1.50, onePager: 2.07 },
];
for (const band of bands) {
  const S = S0 * (1 + band.move);
  const lev = leverageMultiple({ S, daysSinceEntry: MATURITY, sigma: VOL });
  console.log(`${band.label}: computed ${lev.toFixed(2)}x vs one-pager ${band.onePager}x`);
}
```

- [ ] **Step 2: Run the script and record the output**

Run: `node scripts/validate-against-onepager.mjs`

Expected output (already computed by hand during design, for reference — confirm the script reproduces it):

```
--- t=0 sanity check (fee-adjusted entry value) ---
uEthValue(S0, t=0, vol=70%) = 2355.47 (target ~= 2205.00)

--- Terminal payoff (t=24mo) vs. one-pager claims ---
Computed breakeven: $4108 (67.7% from entry)
One-pager claims: breakeven at +60% (~$3,920)

Leverage by band (computed vs. one-pager):
+25% to +54%: computed -1.03x vs one-pager 3.78x
+54% to +75%: computed 0.88x vs one-pager 3.22x
+75% to +125%: computed 2.05x vs one-pager 3.58x
+125% and above: computed 2.51x vs one-pager 2.07x
```

- [ ] **Step 3: Report the finding — do not silently reconcile**

This is a real, material mismatch: the engine (built directly from the 7 real trade legs, summed across all three overlapping tenors as instructed) produces a materially higher breakeven (~68% vs. the claimed 60%) and materially lower leverage in the lower bands than the one-pager states. The most likely cause is that the one-pager's mechanics table describes each tenor's position as an independent "+1x / -0.66x" unit, but the real trade sums the Nov-27 and Feb-28 tranches on top of each other (identical 900/594 sizing in both), which dilutes leverage relative to a single-tranche read of the mechanics table.

Before wiring this engine into the retail UI, surface this discrepancy to the user (Miffy) with the numbers above and ask whether: (a) the retail chart should reflect the engine's real numbers (breakeven ~68%, lower leverage), (b) the trade sizing was meant differently than "sum all three tranches," or (c) something else in the normalization needs revisiting. Do not adjust the engine's math to force a match with the one-pager without that confirmation — the spec is explicit that mismatches get reported, not papered over.

- [ ] **Step 4: Commit**

```bash
git add scripts/validate-against-onepager.mjs
git commit -m "Add one-pager validation script; surfaces a real breakeven/leverage mismatch"
```

---

## Task 8: Assemble the retail-facing HTML artifact

**Files:**
- Create: `artifact/ueth-payoff.html`

**Interfaces:**
- Consumes: the validated logic from Tasks 1–6 (`blackScholesCall`, `normCdf`, `LEGS`/`S0`/`ENTRY_DATE`/`RISK_FREE_RATE`/`computeK`/`daysBetween`/`totalDaysToFinalExpiry`, `valueLeg`, `structureValue`, `uEthValue`, `bisectRoot`, `findBreakeven`, `leverageMultiple`, `scaleLinear`, `buildPayoffPath`) — copied inline (with `export` keywords removed, since this is one plain `<script>`, not a module) so the artifact has zero external file dependencies. `valueLeg`/`structureValue` drop the `entryDate` parameter that the modular versions take, closing over the single `ENTRY_DATE` constant directly instead — the artifact only ever needs one entry date, so threading it through as a parameter would be pure ceremony here. Every other function's logic matches its modular counterpart exactly.

**Note:** Before starting this task, Task 7's finding must have been surfaced to and acknowledged by the user, since it affects what "correct" looks like on this chart. If the user has responded with a preference (e.g., "show the real numbers" vs. "the mechanics table means something different — resize the legs"), apply that decision before building the UI. The markup below assumes option (a) — show the engine's real numbers as-is — since that was the most literal reading of the spec; adjust the constants in `engine/trade.mjs` first (and rerun Tasks 2–7's tests) if the user chooses otherwise.

- [ ] **Step 1: Write the artifact**

Create `artifact/ueth-payoff.html`:

```html
<title>Ultra ETH — Payoff Explorer</title>
<style>
  :root {
    --bg: #f3f0fb;
    --card-bg: #ffffff;
    --text: #1f1a33;
    --muted: #6b6480;
    --accent: #e6299b;
    --accent2: #7c3aed;
    --shadow: 0 8px 24px rgba(90, 60, 150, 0.12);
    --track: #e4defb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #16121f;
      --card-bg: #241f33;
      --text: #f2eefb;
      --muted: #a89fc2;
      --accent: #ff5cbb;
      --accent2: #a78bfa;
      --shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      --track: #3a3350;
    }
  }
  :root[data-theme="dark"] {
    --bg: #16121f; --card-bg: #241f33; --text: #f2eefb; --muted: #a89fc2;
    --accent: #ff5cbb; --accent2: #a78bfa; --shadow: 0 8px 24px rgba(0,0,0,0.4); --track: #3a3350;
  }
  :root[data-theme="light"] {
    --bg: #f3f0fb; --card-bg: #ffffff; --text: #1f1a33; --muted: #6b6480;
    --accent: #e6299b; --accent2: #7c3aed; --shadow: 0 8px 24px rgba(90,60,150,0.12); --track: #e4defb;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 0;
    padding: 24px 16px 64px;
  }
  .page { max-width: 880px; margin: 0 auto; }
  h1 { font-size: 2.2rem; font-weight: 800; margin: 0 0 4px; }
  .subtitle { color: var(--muted); font-size: 1.05rem; margin: 0 0 20px; }
  .card {
    background: var(--card-bg);
    border-radius: 20px;
    box-shadow: var(--shadow);
    padding: 24px;
    margin-bottom: 20px;
  }
  .hero p { line-height: 1.6; }
  .hero ul { line-height: 1.8; padding-left: 20px; }
  .hero strong { color: var(--accent); }
  .controls { display: flex; flex-direction: column; gap: 18px; margin-top: 8px; }
  .control-row { display: flex; flex-direction: column; gap: 6px; }
  .control-row label { font-weight: 600; font-size: 0.9rem; }
  .control-row .value { color: var(--accent); font-weight: 700; }
  input[type="range"] {
    -webkit-appearance: none;
    width: 100%;
    height: 6px;
    border-radius: 999px;
    background: var(--track);
  }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 20px; height: 20px; border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 3px solid var(--card-bg);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .chart-wrap { width: 100%; overflow-x: auto; }
  svg { width: 100%; height: auto; display: block; }
  .axis-label { fill: var(--muted); font-size: 12px; }
  .grid-line { stroke: var(--track); stroke-width: 1; }
  .payoff-path { fill: none; stroke: var(--accent2); stroke-width: 3; }
  .marker-dot { fill: var(--accent); stroke: var(--card-bg); stroke-width: 2; }
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 560px) { .stats { grid-template-columns: 1fr; } }
  .stat-tile {
    background: var(--bg);
    border-radius: 14px;
    padding: 16px;
  }
  .stat-tile .label { color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }
  .stat-tile .big { font-size: 1.5rem; font-weight: 800; }
  .risk-banner {
    background: linear-gradient(135deg, var(--accent2), var(--accent));
    color: white;
    border-radius: 20px;
    padding: 24px;
  }
  .risk-banner h2 { margin-top: 0; }
  .risk-banner p { line-height: 1.6; }
</style>

<div class="page">
  <h1>Ultra ETH</h1>
  <p class="subtitle">One question: what is ETH's price in 2 years?</p>

  <div class="card hero">
    <p>
      If you believe ETH will be anywhere above <strong>$4,000</strong> at the end of
      2 years, uETH is built to be a superior hold to spot or levered ETH.
    </p>
    <ul>
      <li><strong>No liquidations</strong> for 2 years</li>
      <li><strong>No funding rates</strong></li>
      <li>Immediate leveraged exposure from day one</li>
    </ul>
    <p>
      The price of that leverage: your collateral is at risk only if, at the very
      end of the 2-year term, ETH is below the $4,000 target &mdash; not at any
      point during the term itself.
    </p>
  </div>

  <div class="card">
    <h2>Explore the payoff</h2>
    <div class="chart-wrap">
      <svg id="chart" viewBox="0 0 800 440" xmlns="http://www.w3.org/2000/svg">
        <g id="chart-dynamic"></g>
      </svg>
    </div>
    <div class="controls">
      <div class="control-row">
        <label>Time since entry: <span class="value" id="time-label"></span></label>
        <input type="range" id="time-slider" min="0" max="731" step="1" value="0" />
      </div>
      <div class="control-row">
        <label>Volatility: <span class="value" id="vol-label">70%</span></label>
        <input type="range" id="vol-slider" min="20" max="150" step="1" value="70" />
      </div>
      <div class="control-row">
        <label>ETH price marker: <span class="value" id="marker-label"></span></label>
        <input type="range" id="marker-slider" min="0" max="9800" step="10" value="2450" />
      </div>
    </div>
  </div>

  <div class="card">
    <div class="stats">
      <div class="stat-tile">
        <div class="label">Breakeven ETH price</div>
        <div class="big" id="breakeven-stat">&mdash;</div>
      </div>
      <div class="stat-tile">
        <div class="label">uETH value at marker price</div>
        <div class="big" id="marker-stat">&mdash;</div>
      </div>
    </div>
  </div>

  <div class="card risk-banner">
    <h2>Risk</h2>
    <p>
      <strong>Price risk:</strong> this product is for ETH bulls. If ETH is not
      above the target price at the end of the 2-year term, your collateral is at
      risk in line with the curve above.
    </p>
    <p>
      <strong>Counterparty risk:</strong> the options behind this structure are
      sourced from vetted OTC option desk partners across a diversified set of
      counterparties.
    </p>
    <p>
      <strong>Fee:</strong> uETH charges a 10% fee on deposited principal at
      entry &mdash; a 1 ETH deposit is immediately worth about 0.9 ETH of exposure
      before the market moves.
    </p>
  </div>
</div>

<script>
(function () {
  // --- Engine (copied from engine/*.mjs, `export` removed — single inline script) ---
  function erf(x) {
    const sign = x < 0 ? -1 : 1;
    x = Math.abs(x);
    const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
    const t = 1 / (1 + p * x);
    const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return sign * y;
  }
  function normCdf(x) { return 0.5 * (1 + erf(x / Math.SQRT2)); }
  function blackScholesCall({ S, K, T, sigma, r }) {
    const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
    const d2 = d1 - sigma * Math.sqrt(T);
    return S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
  }

  const S0 = 2450;
  const ENTRY_DATE = '2026-08-24';
  const RISK_FREE_RATE = 0.02;
  const FEE_RATE = 0.10;
  const LEGS = [
    { dir: 1, qty: 900, strike: 3062.5, expiry: '2027-11-24', premium: 507.80 },
    { dir: -1, qty: 594, strike: 5512.5, expiry: '2027-11-24', premium: 136.22 },
    { dir: 1, qty: 900, strike: 3062.5, expiry: '2028-02-24', premium: 584.61 },
    { dir: -1, qty: 594, strike: 5512.5, expiry: '2028-02-24', premium: 186.85 },
    { dir: 1, qty: 225, strike: 3062.5, expiry: '2028-08-24', premium: 719.56 },
    { dir: 1, qty: 225, strike: 4287.5, expiry: '2028-08-24', premium: 473.43 },
    { dir: 1, qty: 225, strike: 5512.5, expiry: '2028-08-24', premium: 342.66 },
  ];

  function toUTCms(iso) { const [y, m, d] = iso.split('-').map(Number); return Date.UTC(y, m - 1, d); }
  function daysBetween(a, b) { return Math.round((toUTCms(b) - toUTCms(a)) / 86400000); }

  const TOTAL_ENTRY_COST = LEGS.reduce((sum, leg) => sum + leg.dir * leg.qty * leg.premium, 0);
  const K = TOTAL_ENTRY_COST / ((1 - FEE_RATE) * S0);
  const MATURITY_DAYS = daysBetween(ENTRY_DATE, '2028-08-24');

  function valueLeg(leg, { S, daysSinceEntry, sigma }) {
    const daysToLegExpiry = daysBetween(ENTRY_DATE, leg.expiry);
    if (daysSinceEntry >= daysToLegExpiry) return Math.max(S - leg.strike, 0);
    const T = (daysToLegExpiry - daysSinceEntry) / 365;
    return blackScholesCall({ S, K: leg.strike, T, sigma, r: RISK_FREE_RATE });
  }
  function structureValue({ S, daysSinceEntry, sigma }) {
    return LEGS.reduce((sum, leg) => sum + leg.dir * leg.qty * valueLeg(leg, { S, daysSinceEntry, sigma }), 0);
  }
  function uEthValue(args) { return structureValue(args) / K; }

  function bisectRoot(f, lo, hi, iterations) {
    iterations = iterations || 60;
    let a = lo, b = hi, fa = f(a);
    const fb = f(b);
    if (fa === 0) return a;
    if (fb === 0) return b;
    if (Math.sign(fa) === Math.sign(fb)) return null;
    for (let i = 0; i < iterations; i++) {
      const mid = (a + b) / 2, fm = f(mid);
      if (fm === 0) return mid;
      if (Math.sign(fm) === Math.sign(fa)) { a = mid; fa = fm; } else { b = mid; }
    }
    return (a + b) / 2;
  }
  function findBreakeven({ daysSinceEntry, sigma }) {
    return bisectRoot((S) => uEthValue({ S, daysSinceEntry, sigma }) - S, 1, 20000);
  }
  function leverageMultiple({ S, daysSinceEntry, sigma }) {
    const spotReturn = S / S0 - 1;
    if (Math.abs(spotReturn) < 1e-9) return null;
    const uReturn = uEthValue({ S, daysSinceEntry, sigma }) / S0 - 1;
    return uReturn / spotReturn;
  }

  function scaleLinear({ domain, range }) {
    const d0 = domain[0], d1 = domain[1], r0 = range[0], r1 = range[1];
    return (x) => r0 + ((x - d0) * (r1 - r0)) / (d1 - d0);
  }
  function buildPayoffPath({ points, xScale, yScale }) {
    return points.map((p, i) => (i === 0 ? 'M' : 'L') + xScale(p.S).toFixed(2) + ',' + yScale(p.value).toFixed(2)).join(' ');
  }

  // --- UI wiring ---
  const timeSlider = document.getElementById('time-slider');
  const volSlider = document.getElementById('vol-slider');
  const markerSlider = document.getElementById('marker-slider');
  const timeLabel = document.getElementById('time-label');
  const volLabel = document.getElementById('vol-label');
  const markerLabel = document.getElementById('marker-label');
  const breakevenStat = document.getElementById('breakeven-stat');
  const markerStat = document.getElementById('marker-stat');
  const chartDynamic = document.getElementById('chart-dynamic');

  timeSlider.max = String(MATURITY_DAYS);

  const fmtUsd = (n) => '$' + Math.round(n).toLocaleString('en-US');
  const fmtDate = (days) => new Date(toUTCms(ENTRY_DATE) + days * 86400000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  const margin = { top: 20, right: 20, bottom: 40, left: 70 };
  const width = 800, height = 440;
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const xMax = 4 * S0;

  function render() {
    const daysSinceEntry = Number(timeSlider.value);
    const sigma = Number(volSlider.value) / 100;
    const markerS = Number(markerSlider.value);

    timeLabel.textContent = fmtDate(daysSinceEntry);
    volLabel.textContent = Number(volSlider.value) + '%';
    markerLabel.textContent = fmtUsd(markerS);

    const N = 121;
    const points = [];
    for (let i = 0; i < N; i++) {
      const S = (xMax * i) / (N - 1);
      points.push({ S, value: uEthValue({ S, daysSinceEntry, sigma }) });
    }
    const values = points.map((p) => p.value);
    const yMin = Math.min(0, ...values);
    const yMax = Math.max(...values) * 1.05;

    const xScale = scaleLinear({ domain: [0, xMax], range: [margin.left, margin.left + plotW] });
    const yScale = scaleLinear({ domain: [yMin, yMax], range: [margin.top + plotH, margin.top] });

    const path = buildPayoffPath({ points, xScale, yScale });
    const markerValue = uEthValue({ S: markerS, daysSinceEntry, sigma });
    const markerX = xScale(markerS);
    const markerY = yScale(markerValue);

    const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * xMax);
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => yMin + f * (yMax - yMin));

    let svg = '';
    for (const t of xTicks) {
      const x = xScale(t);
      svg += '<line class="grid-line" x1="' + x + '" y1="' + margin.top + '" x2="' + x + '" y2="' + (margin.top + plotH) + '"/>';
      svg += '<text class="axis-label" x="' + x + '" y="' + (margin.top + plotH + 20) + '" text-anchor="middle">' + fmtUsd(t) + '</text>';
    }
    for (const t of yTicks) {
      const y = yScale(t);
      svg += '<line class="grid-line" x1="' + margin.left + '" y1="' + y + '" x2="' + (margin.left + plotW) + '" y2="' + y + '"/>';
      svg += '<text class="axis-label" x="' + (margin.left - 10) + '" y="' + (y + 4) + '" text-anchor="end">' + fmtUsd(t) + '</text>';
    }
    svg += '<path class="payoff-path" d="' + path + '"/>';
    svg += '<circle class="marker-dot" cx="' + markerX + '" cy="' + markerY + '" r="6"/>';
    chartDynamic.innerHTML = svg;

    const breakeven = findBreakeven({ daysSinceEntry, sigma });
    breakevenStat.textContent = breakeven ? fmtUsd(breakeven) + ' (' + ((breakeven / S0 - 1) * 100).toFixed(0) + '% from entry)' : 'N/A';

    const lev = leverageMultiple({ S: markerS, daysSinceEntry, sigma });
    markerStat.textContent = fmtUsd(markerValue) + (lev === null ? '' : ' (' + lev.toFixed(2) + 'x)');
  }

  timeSlider.addEventListener('input', render);
  volSlider.addEventListener('input', render);
  markerSlider.addEventListener('input', render);
  render();
})();
</script>
```

- [ ] **Step 2: Commit**

```bash
git add artifact/ueth-payoff.html
git commit -m "Assemble retail-facing uETH payoff interactive artifact"
```

---

## Task 9: Manual QA and publish

**Files:** none (verification + Artifact tool usage only)

**Interfaces:** none — this task drives the browser/Artifact tool, it doesn't produce code consumed by other tasks.

- [ ] **Step 1: Open the artifact locally and sanity-check it renders**

Run: `open artifact/ueth-payoff.html` (macOS) and confirm in a real browser:
- The hero, chart card, stat tiles, and risk banner all render without console errors.
- Dragging the time slider changes the date label and visibly reshapes the curve (it should show kinks as tranches cross their own expiry).
- Dragging the vol slider changes the curve when `daysSinceEntry < 731` (before full maturity) and has **no** effect on the curve once `daysSinceEntry = 731` (all legs expired, pure intrinsic value) — verify this specifically, it's a direct consequence of the roll-off logic in Task 3.
- Dragging the marker slider moves the dot along the curve and updates the "uETH value at marker price" stat tile.
- No horizontal scrollbar on the page itself; the chart scrolls in its own container only if the viewport is very narrow.

- [ ] **Step 2: Check dark mode**

Toggle the OS/browser to dark mode (or use browser devtools to force `prefers-color-scheme: dark`) and confirm text stays readable and the accent colors still read clearly against the dark card backgrounds.

- [ ] **Step 3: Publish via the Artifact tool**

Use the Artifact tool with `file_path` pointing at `artifact/ueth-payoff.html`, a `favicon` (pick one emoji, e.g. "📈"), and a one-sentence `description` (e.g., "Interactive payoff explorer for the Ultra ETH structured product"). Report the resulting URL to the user.

- [ ] **Step 4: Report Task 7's finding alongside the published link**

When reporting the artifact link to the user, restate the breakeven/leverage mismatch from Task 7 (computed ~68% breakeven and lower leverage bands vs. the one-pager's claimed 60%/3.78x-3.22x-3.58x-2.07x) so it isn't lost between task handoffs — the shipped artifact currently shows the engine's real numbers, not the one-pager's numbers, per the most literal reading of "price off the real trade legs."
