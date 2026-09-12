/**
 * The report, in a browser.
 *
 * Design read: a result slip that shows its working. Each run's rate with the range it is
 * actually consistent with, drawn as a band rather than printed as a bare percentage - which
 * is the one thing this tool will not do - and the verdict underneath in plain words.
 *
 * The bands are deliberately NOT the argument. Two intervals overlapping is not the test and
 * the page says so: the verdict comes from the items the runs disagreed on, because those are
 * the only ones that carry any information about which is better. Drawing the bands and
 * letting a reader conclude from their overlap would be the exact overclaim this tool exists
 * to refuse.
 */
import {
  mcnemar,
  pairedNeeded,
  unpairedNeeded,
  wilson,
  type Discordance,
  type Interval,
} from "./stats.js";
import { createThemeStore, DEFAULT_THEME, grouped, type Theme } from "./lib/theme.js";
import { wirePalette } from "./lib/palette-keys.js";

const field = (id: string) => document.getElementById(id) as HTMLInputElement;
const cells = ["both", "onlyA", "onlyB", "neither"] as const;

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

function read(): Discordance {
  const value = (id: string) => Math.max(0, Math.floor(Number(field(id).value) || 0));
  return { both: value("both"), onlyA: value("onlyA"), onlyB: value("onlyB"), neither: value("neither") };
}

function band(label: string, interval: Interval): HTMLElement {
  const row = document.createElement("div");
  row.className = "rate";
  row.dataset.run = label;

  const name = document.createElement("span");
  name.className = "rate-name";
  name.textContent = label;

  const track = document.createElement("span");
  track.className = "rate-track";
  const range = document.createElement("i");
  range.className = "rate-range";
  range.style.left = `${interval.low * 100}%`;
  range.style.width = `${(interval.high - interval.low) * 100}%`;
  const point = document.createElement("b");
  point.className = "rate-point";
  point.style.left = `${interval.point * 100}%`;
  track.append(range, point);

  const figure = document.createElement("span");
  figure.className = "rate-figure";
  // Never a bare percentage. The interval is part of the number, not a footnote to it.
  figure.textContent = `${pct(interval.point)} [${pct(interval.low)} to ${pct(interval.high)}] n=${interval.n}`;

  row.append(name, track, figure);
  return row;
}

function update(): void {
  const table = read();
  const n = table.both + table.onlyA + table.onlyB + table.neither;
  const shape = document.getElementById("shape")!;
  const rates = document.getElementById("rates")!;
  const verdict = document.getElementById("verdict")!;
  const settle = document.getElementById("settle")!;

  const discordant = table.onlyA + table.onlyB;
  shape.textContent =
    n === 0
      ? "No items yet."
      : `${n} items. ${discordant} of them separated the runs (${table.onlyA} only A, ${table.onlyB} only B).`;

  const a = wilson(table.both + table.onlyA, n);
  const b = wilson(table.both + table.onlyB, n);
  rates.replaceChildren(band("A", a), band("B", b));

  if (n === 0) {
    verdict.textContent = "Nothing measured, so every rate is still possible.";
    verdict.dataset.separated = "unknown";
    settle.textContent = "";
    return;
  }

  const { p, method } = mcnemar(table);
  const separated = p < 0.05;
  const points = (b.point - a.point) * 100;
  verdict.dataset.separated = String(separated);
  verdict.textContent = separated
    ? `B is ahead by ${points.toFixed(1)} points, and that is distinguishable from noise at this sample size, p = ${p.toFixed(4)} (${method}).`
    : `${points >= 0 ? "B" : "A"} is ahead by ${Math.abs(points).toFixed(1)} points, and that is indistinguishable from noise at this sample size, p = ${p.toFixed(4)} (${method}).`;

  /*
   * What would settle it, beside what did not. A verdict of "not shown" with no number is
   * where a reader decides the tool is being difficult; the number is what makes it a plan.
   */
  const paired = pairedNeeded(discordant / n, Math.abs(b.point - a.point));
  const unpaired = unpairedNeeded(a.point, b.point);
  settle.textContent =
    paired === null
      ? "There is no difference to size: no number of items detects one that is not there."
      : `About ${paired} items each would settle a difference this size, given how often these two disagree.` +
        (unpaired === null ? "" : ` A test that ignored the pairing would ask for ${unpaired}.`);
}

for (const id of cells) field(id).addEventListener("input", update);
update();

/* ---- palette ---------------------------------------------------------------------------- */

const THEMES = (await fetch("./theme/palettes.json").then((r) => r.json())) as Theme[];
const store = createThemeStore(THEMES, "twilight-comet", "discern:theme");
let chosen = store.initial();

document.getElementById("palette-host")!.innerHTML = `
  <section class="palette">
    <button class="palette-toggle" type="button" aria-expanded="false" aria-controls="palette-list">
      <span class="palette-chip" aria-hidden="true" id="chip"></span>
      <span class="sr-only">Palette: </span><span id="palette-name"></span>
    </button>
    <div class="palette-list" id="palette-list" hidden></div>
  </section>`;

const plist = document.getElementById("palette-list")!;
const toggle = document.querySelector<HTMLButtonElement>(".palette-toggle")!;
const chip = document.getElementById("chip")!;
const nameOut = document.getElementById("palette-name")!;
const options: HTMLElement[] = [];

for (const group of grouped(THEMES)) {
  const set = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = group.label;
  set.append(legend);
  for (const t of group.themes) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.theme = t.id;
    // data-theme on the CHIP too: on the button alone it rescopes --fg and --dim, so the
    // option's own label gets painted in a palette the page is not showing.
    const swatch = document.createElement("span");
    swatch.className = "palette-chip";
    swatch.setAttribute("aria-hidden", "true");
    swatch.dataset.theme = t.id;
    btn.append(swatch, t.label);
    options.push(btn);
    set.append(btn);
  }
  plist.append(set);
}

function select(id: string): void {
  chosen = store.apply(id);
  nameOut.textContent = THEMES.find((x) => x.id === chosen)?.label ?? "Palette";
  chip.dataset.theme = chosen;
}

function setOpen(open: boolean): void {
  toggle.setAttribute("aria-expanded", String(open));
  plist.hidden = !open;
  if (!open) toggle.focus();
}

const picker = wirePalette(plist, options, { select, current: () => chosen, onEscape: () => setOpen(false) });
toggle.addEventListener("click", () => setOpen(toggle.getAttribute("aria-expanded") !== "true"));
select(chosen);
picker.refresh();
