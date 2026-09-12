import { expect, test } from "@playwright/test";

const set = async (page: import("@playwright/test").Page, t: Record<string, number>) => {
  for (const [id, v] of Object.entries(t)) await page.locator(`#${id}`).fill(String(v));
  /*
   * Wait on the REPORT, not on the prose beside it.
   *
   * The first version waited for "N items" in the summary line, which says "No items yet."
   * when N is zero - so the one case worth testing, n = 0, timed out on the helper rather
   * than on anything about the page. Every rate carries its n, always, in every state.
   */
  const n = Object.values(t).reduce((a, b) => a + b, 0);
  await expect
    .poll(() => page.locator(".rate-figure").first().textContent())
    .toContain(`n=${n}`);
};

test("the server under test is this app, not another app on the same port", async ({ page }) => {
  await page.goto("./");
  await expect(page).toHaveTitle(/^discern/);
});

test("it reproduces the example printed on the front page of the repository", async ({ page }) => {
  await page.goto("./");
  await set(page, { both: 16, onlyA: 0, onlyB: 2, neither: 2 });

  /*
   * The README shows this exact run, produced by the PYTHON. Every figure here comes from
   * the TypeScript port, so matching it is an end-to-end check that the port did not drift -
   * a stronger one than any vector, because it is the output somebody already published.
   */
  const figures = await page.locator(".rate-figure").allTextContents();
  expect(figures[0]).toBe("80.0% [58.4% to 91.9%] n=20");
  expect(figures[1]).toBe("90.0% [69.9% to 97.2%] n=20");
  await expect(page.locator("#verdict")).toContainText("indistinguishable from noise");
  await expect(page.locator("#verdict")).toContainText("p = 0.5000");
  await expect(page.locator("#settle")).toContainText("About 77 items each");
});

test("it agrees with the figure the Python's own comment cites", async ({ page }) => {
  await page.goto("./");
  // stats.py argues for the continuity correction with b=30, c=12, where it says the exact
  // test gives 0.0079. If the port disagreed here, the argument in that comment would be
  // about a different implementation.
  await set(page, { both: 100, onlyA: 12, onlyB: 30, neither: 100 });
  await expect(page.locator("#verdict")).toContainText("p = 0.0079");
  await expect(page.locator("#verdict")).toContainText("distinguishable from noise");
  await expect(page.locator("#verdict")).toHaveAttribute("data-separated", "true");
});

test("it never prints a bare percentage", async ({ page }) => {
  await page.goto("./");
  await set(page, { both: 20, onlyA: 0, onlyB: 0, neither: 0 });

  // The rule the whole tool is built on. 20 of 20 is where a Wald interval has zero width
  // and would print 100% with nothing beside it.
  for (const figure of await page.locator(".rate-figure").allTextContents()) {
    expect(figure).toMatch(/\[.+ to .+\]/);
    expect(figure).toContain("n=");
  }
});

test("it says what would settle a difference it cannot call", async ({ page }) => {
  await page.goto("./");
  await set(page, { both: 16, onlyA: 0, onlyB: 2, neither: 2 });

  // A verdict of "not shown" with no number is where a reader decides the tool is being
  // difficult. The number is what turns a refusal into a plan.
  await expect(page.locator("#settle")).toContainText(/About \d+ items each/);
  // And the unpaired figure beside it, which is the number a tool ignoring pairing asks for.
  await expect(page.locator("#settle")).toContainText(/would ask for \d+/);
});

test("it refuses to let the bands be read as the test", async ({ page }) => {
  await page.goto("./");
  // The bands overlap here AND the difference is real, which is exactly the case that makes
  // "overlapping means the same" wrong. The caution is on the page before anybody meets it.
  await set(page, { both: 100, onlyA: 12, onlyB: 30, neither: 100 });

  const overlap = await page.locator(".rate-range").evaluateAll((els) => {
    const [a, b] = els.map((e) => e.getBoundingClientRect());
    return a!.left < b!.right && b!.left < a!.right;
  });
  expect(overlap, "the bands do not overlap here, so this proves nothing").toBe(true);
  await expect(page.locator("#verdict")).toHaveAttribute("data-separated", "true");
  await expect(page.locator(".caution")).toContainText("The bands are not the test");
});

test("nothing measured is an answer, not a crash", async ({ page }) => {
  await page.goto("./");
  await set(page, { both: 0, onlyA: 0, onlyB: 0, neither: 0 });

  // n = 0 is where a Wilson interval is the whole of [0, 1] and a naive one divides by zero.
  await expect(page.locator("#verdict")).toContainText("every rate is still possible");
  const figures = await page.locator(".rate-figure").allTextContents();
  for (const f of figures) expect(f).toContain("[0.0% to 100.0%]");
});
