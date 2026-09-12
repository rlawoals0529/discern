import { describe, expect, it } from "vitest";
import vectors from "./vectors.json" with { type: "json" };
import {
  erf,
  erfc,
  mcnemar,
  pairedNeeded,
  unpairedNeeded,
  wald,
  wilson,
  Z_95,
  type Discordance,
} from "./stats.js";

/**
 * The port, judged against the Python it is a port OF.
 *
 * Every expected value in site/vectors.json was produced by running src/discern/stats.py,
 * not by running this file and writing down what it said. That is the whole point: a port
 * tested against itself proves it is self-consistent, and self-consistency is not the
 * property anybody wants from a second implementation of a statistic.
 *
 * scripts/export_vectors.py regenerates the file and CI fails if it has moved, so the
 * vectors cannot quietly become whatever this code happens to produce.
 */

/** Tight. These are the same formulae in two languages, not two approximations of one. */
const CLOSE = 1e-12;

describe("the vectors are the Python's, and there are enough of them", () => {
  it("covers every function the page uses", () => {
    for (const name of ["wilson", "wald", "mcnemar", "paired_n_needed", "unpaired_n_needed", "erf", "erfc"] as const) {
      expect(vectors[name].length, name).toBeGreaterThan(4);
    }
  });

  it("agrees with the Python about the constant everything is scaled by", () => {
    expect(Z_95).toBeCloseTo(vectors.z95, 15);
  });
});

describe("wilson", () => {
  for (const v of vectors.wilson) {
    it(`${v.successes} of ${v.n}`, () => {
      const got = wilson(v.successes, v.n);
      expect(got.point).toBeCloseTo(v.expected.point, 12);
      expect(got.low).toBeCloseTo(v.expected.low, 12);
      expect(got.high).toBeCloseTo(v.expected.high, 12);
      expect(got.n).toBe(v.expected.n);
    });
  }
});

describe("wald", () => {
  for (const v of vectors.wald) {
    it(`${v.successes} of ${v.n}`, () => {
      const got = wald(v.successes, v.n);
      expect(got.low).toBeCloseTo(v.expected.low, 12);
      expect(got.high).toBeCloseTo(v.expected.high, 12);
    });
  }
});

describe("mcnemar", () => {
  for (const v of vectors.mcnemar) {
    const t = v.table as Discordance;
    it(`${t.onlyA} vs ${t.onlyB} discordant`, () => {
      const got = mcnemar(t);
      expect(got.method).toBe(v.expected.method);
      // Relative, because a p-value spans orders of magnitude and an absolute tolerance
      // would wave through a wrong answer in the tail, which is where it matters.
      expect(got.p).toBeCloseTo(v.expected.p, 12);
      if (v.expected.p > 0) expect(Math.abs(got.p / v.expected.p - 1)).toBeLessThan(1e-10);
    });
  }
});

describe("sample sizes", () => {
  for (const v of vectors.paired_n_needed) {
    it(`paired: ${v.effect} at ${v.p_discordant} discordant`, () => {
      expect(pairedNeeded(v.p_discordant, v.effect)).toBe(v.expected);
    });
  }
  for (const v of vectors.unpaired_n_needed) {
    it(`unpaired: ${v.p1} against ${v.p2}`, () => {
      expect(unpairedNeeded(v.p1, v.p2)).toBe(v.expected);
    });
  }
});

describe("erf and erfc", () => {
  /*
   * The one thing that is not a transcription. JavaScript has no erf, so the port
   * reimplements one out of two standard expansions - and these are the only reason to
   * believe it. The tail matters as much as the middle: erfc is what a chi-square upper tail
   * is made of, so an absolute tolerance there would pass anything.
   */
  for (const v of vectors.erf) {
    it(`erf(${v.x})`, () => expect(erf(v.x)).toBeCloseTo(v.expected, 14));
  }
  for (const v of vectors.erfc) {
    it(`erfc(${v.x})`, () => {
      expect(erfc(v.x)).toBeCloseTo(v.expected, 14);
      if (v.expected > 0) expect(Math.abs(erfc(v.x) / v.expected - 1)).toBeLessThan(1e-10);
    });
  }
});
