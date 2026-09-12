/**
 * A port of src/discern/stats.py, so the same report can be produced in a browser.
 *
 * A second implementation of a statistic is a second implementation, and this one is not
 * trusted on its own account: `scripts/export_vectors.py` runs the PYTHON over a spread of
 * inputs and writes the answers to `site/vectors.json`, and `stats.test.ts` runs this code
 * against those. A port tested only against itself proves that it is self-consistent, which
 * is not the property anybody wants from it.
 *
 * Everything here is a transcription. Where Python has something JavaScript does not - exact
 * integer arithmetic, `math.erf`, `math.comb` - the substitution is named at the point it
 * happens, because that is where a port stops being a transcription and starts being a
 * rewrite.
 */

/** 1.959963985 — the same two-sided 95% constant the Python uses. */
export const Z_95 = 1.959963984540054;

export interface Interval {
  point: number;
  low: number;
  high: number;
  n: number;
}

export const width = (i: Interval): number => i.high - i.low;
export const overlaps = (a: Interval, b: Interval): boolean => a.low <= b.high && b.low <= a.high;

/**
 * A Wilson score interval for a proportion.
 *
 * Defined for n = 0, where it returns the whole of [0, 1]: nothing was measured, so every
 * proportion is consistent with what was seen.
 */
export function wilson(successes: number, n: number, z: number = Z_95): Interval {
  if (n < 0 || successes < 0 || successes > n) {
    throw new Error(`${successes} successes out of ${n} is not a proportion`);
  }
  if (n === 0) return { point: 0, low: 0, high: 1, n: 0 };

  const p = successes / n;
  const denominator = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / denominator;
  const spread = (z / denominator) * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return { point: p, low: Math.max(0, centre - spread), high: Math.min(1, centre + spread), n };
}

/** The interval this tool does not use, kept so the page can show why. */
export function wald(successes: number, n: number, z: number = Z_95): Interval {
  if (n === 0) return { point: 0, low: 0, high: 0, n: 0 };
  const p = successes / n;
  const spread = z * Math.sqrt((p * (1 - p)) / n);
  return { point: p, low: p - spread, high: p + spread, n };
}

export interface Discordance {
  both: number;
  onlyA: number;
  onlyB: number;
  neither: number;
}

export const discordant = (t: Discordance): number => t.onlyA + t.onlyB;
export const total = (t: Discordance): number => t.both + t.onlyA + t.onlyB + t.neither;

/** Where the exact test stops being affordable, not where it stops being right. */
export const EXACT_BELOW_DISCORDANT = 2000;

export type Method = "mcnemar-exact" | "mcnemar-chi2";

/**
 * Two-sided McNemar over the discordant pairs. Returns the p-value and the method used.
 *
 * With no discordant pairs there is nothing to test: the runs agreed on every item, so p is
 * 1 by definition rather than by convention.
 */
export function mcnemar(table: Discordance): { p: number; method: Method } {
  const b = table.onlyA;
  const c = table.onlyB;
  if (b + c === 0) return { p: 1, method: "mcnemar-exact" };

  if (b + c < EXACT_BELOW_DISCORDANT) {
    /*
     * Exact two-sided binomial on the discordant pairs, against p = 0.5.
     *
     * BigInt, where the Python has plain ints. The sum of binomial coefficients and the 2^n
     * beneath it both run past what a double can hold long before 2000 - 2^-2000 is simply
     * zero in float64 - so the tail is summed exactly and the division is done once, scaled
     * by 2^64 to keep the bits that matter.
     */
    const k = Math.min(b, c);
    const t = b + c;
    let sum = 0n;
    let term = 1n; // C(t, 0)
    for (let i = 0; i <= k; i++) {
      sum += term;
      term = (term * BigInt(t - i)) / BigInt(i + 1);
    }
    const SCALE = 1n << 64n;
    const tail = Number((sum * SCALE) >> BigInt(t)) / Number(SCALE);
    return { p: Math.min(1, 2 * tail), method: "mcnemar-exact" };
  }

  // With the continuity correction, which is not a detail: the uncorrected form is
  // anti-conservative, and a tool arguing against calling differences that are not there
  // must not lean that way.
  const chi2 = (Math.abs(b - c) - 1) ** 2 / (b + c);
  return { p: chi2SurvivalOneDf(chi2), method: "mcnemar-chi2" };
}

/** Upper tail of a chi-square with one degree of freedom: P(X > x) = erfc(sqrt(x/2)). */
export function chi2SurvivalOneDf(x: number): number {
  if (x <= 0) return 1;
  return erfc(Math.sqrt(x / 2));
}

/**
 * Pairs needed to detect this difference, given how often the runs disagree.
 *
 * Returns null when the effect is zero: no sample size detects a difference that is not
 * there, and a large number would read as "collect this many and you will know".
 */
export function pairedNeeded(
  pDiscordant: number,
  effect: number,
  alpha = 0.05,
  power = 0.8,
): number | null {
  if (effect <= 0 || pDiscordant <= 0) return null;
  const za = zTwoSided(alpha);
  const zb = zOneSided(1 - power);
  const n =
    ((za * Math.sqrt(pDiscordant) + zb * Math.sqrt(pDiscordant - effect ** 2)) / effect) ** 2;
  return Math.ceil(n);
}

/** Per-arm size the UNPAIRED test would demand, so the difference between them is visible. */
export function unpairedNeeded(p1: number, p2: number, alpha = 0.05, power = 0.8): number | null {
  if (p1 === p2) return null;
  const za = zTwoSided(alpha);
  const zb = zOneSided(1 - power);
  const pBar = (p1 + p2) / 2;
  const numerator =
    (za * Math.sqrt(2 * pBar * (1 - pBar)) + zb * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2;
  return Math.ceil(numerator / (p1 - p2) ** 2);
}

const zTwoSided = (alpha: number): number => inverseNormal(1 - alpha / 2);
const zOneSided = (beta: number): number => inverseNormal(1 - beta);

/**
 * The standard normal quantile, by bisection on erf - the same method the Python uses.
 *
 * A rational approximation would be faster and is what most code reaches for. This is called
 * a handful of times per report, so the slower method is free, and it removes a table of
 * magic constants nobody can check by eye.
 */
export function inverseNormal(p: number): number {
  if (!(p > 0 && p < 1)) throw new Error(`${p} is not a probability strictly between 0 and 1`);
  let low = -12;
  let high = 12;
  for (let i = 0; i < 200; i++) {
    const mid = (low + high) / 2;
    if (0.5 * (1 + erf(mid / Math.SQRT2)) < p) low = mid;
    else high = mid;
  }
  return (low + high) / 2;
}

/*
 * erf and erfc, which JavaScript does not have and Python does.
 *
 * This is the one place the port is not a transcription, so it is the one place worth being
 * careful. Two standard expansions rather than a table of fitted constants: the Maclaurin
 * series where it converges quickly, and Lentz's method on the continued fraction for the
 * complementary function in the tail. Both are checked against the Python's own values in
 * site/stats.test.ts, which is the only reason to believe either of them.
 */

/** Maclaurin series. Converges fast for small |x| and slowly past about 3. */
function erfSeries(x: number): number {
  let term = x;
  let sum = x;
  for (let n = 1; n < 200; n++) {
    term *= (-x * x) / n;
    const add = term / (2 * n + 1);
    sum += add;
    if (Math.abs(add) < Math.abs(sum) * 1e-17) break;
  }
  return (2 / Math.sqrt(Math.PI)) * sum;
}

/** Continued fraction for erfc, by Lentz's method. The tail, where the series is useless. */
function erfcContinued(x: number): number {
  const tiny = 1e-300;
  let f = tiny;
  let c = f;
  let d = 0;
  for (let i = 1; i < 300; i++) {
    // erfc(x) = exp(-x^2)/sqrt(pi) * 1/(x + (1/2)/(x + 1/(x + (3/2)/(x + ...))))
    const a = i === 1 ? 1 : (i - 1) / 2;
    const b = x;
    d = b + a * d;
    if (d === 0) d = tiny;
    c = b + a / c;
    if (c === 0) c = tiny;
    d = 1 / d;
    const delta = c * d;
    f *= delta;
    if (Math.abs(delta - 1) < 1e-17) break;
  }
  return (Math.exp(-x * x) / Math.sqrt(Math.PI)) * f;
}

export function erf(x: number): number {
  if (x < 0) return -erf(-x);
  if (x > 6) return 1; // erfc(6) is 2e-17; the difference is below a double's resolution at 1.
  return x < 2 ? erfSeries(x) : 1 - erfcContinued(x);
}

export function erfc(x: number): number {
  if (x < 0) return 2 - erfc(-x);
  return x < 2 ? 1 - erfSeries(x) : erfcContinued(x);
}
