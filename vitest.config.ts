import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    /* Named, not the default glob: that also matches *.spec.ts and would collect the
       Playwright suite, failing it with "Playwright Test did not expect test() to be called
       here". */
    include: ["site/**/*.test.ts"],
  },
  resolve: {
    alias: [
      /*
       * Relative `.js` imports resolve to the TypeScript, not to the build beside it.
       *
       * The page loads compiled modules from the same directory as their sources - that is
       * what lets it be plain HTML with no bundler. The cost is that `import "./stats.js"`
       * in a test resolves to the COMPILED file, which is whatever the last build produced.
       * Without this, the vector suite was checking a stale artifact: a `throw` planted in
       * wilson() left all 80 of them green.
       *
       * Vitest would resolve .js to .ts on its own if the .js were not sitting there. It is,
       * so this says which one is meant.
       */
      { find: /^(\.{1,2}\/.*)\.js$/, replacement: "$1.ts" },
    ],
  },
});
