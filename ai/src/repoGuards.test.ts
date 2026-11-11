import { describe, expect, it } from "vitest";

import packageJson from "../../package.json";

// Plan Task 10 Step 1. Vitest does not type-check, and its include glob only
// collects `*.test.ts`. Two silent ways to report green on a broken tree follow
// from that, and each gets a guard here. Every expectation is a literal.

describe("the test gate type-checks before it runs the tests", () => {
  it("has a typecheck script that is exactly `tsc --noEmit`", () => {
    expect(packageJson.scripts.typecheck).toBe("tsc --noEmit");
  });

  it("`npm test` runs the type check first and vitest after it", () => {
    const steps = packageJson.scripts.test.split("&&").map((s) => s.trim());
    expect(steps[0]).toBe("npm run typecheck");
    expect(steps.length).toBeGreaterThanOrEqual(2);
    expect(steps.slice(1).some((s) => s.startsWith("vitest run"))).toBe(true);
  });
});

// Keys are relative to this file ("../../frontend/src/x.test.tsx"). Vite's glob
// import only accepts literal patterns, hence the repetition. The negations prune
// build output, the (symlinked) virtualenv and agent scratch directories;
// node_modules is skipped by Vite itself.
const testTsx = Object.keys(
  import.meta.glob([
    "../../**/*.test.tsx",
    "!../../node_modules/**",
    "!../../.venv/**",
    "!../../dist/**",
    "!../../.git/**",
    "!../../.claude/**",
    "!../../.superpowers/**",
  ]),
);
const testTs = Object.keys(
  import.meta.glob([
    "../../**/*.test.ts",
    "!../../node_modules/**",
    "!../../.venv/**",
    "!../../dist/**",
    "!../../.git/**",
    "!../../.claude/**",
    "!../../.superpowers/**",
  ]),
);

describe("no test file is silently skipped by the vitest include globs", () => {
  it("pins the include globs this guard reasons about", async () => {
    const { default: config } = await import("../../vitest.config");
    expect(config.test?.include).toEqual([
      "ai/src/**/*.test.ts",
      "frontend/src/**/*.test.ts",
    ]);
  });

  it("finds the test files it is supposed to police (the glob itself works)", () => {
    // (Vite's glob omits the importing file itself, so look for its neighbours.)
    expect(testTs).toContain("./alertFsm.test.ts");
    expect(testTs).toContain("../../frontend/src/api/client.test.ts");
    expect(testTs.length).toBeGreaterThan(10);
  });

  it("there is no *.test.tsx anywhere: the .ts-only glob would skip it and exit 0", () => {
    expect(testTsx).toEqual([]);
  });

  it("every *.test.ts lives under ai/src or frontend/src, where the glob looks", () => {
    // From this file (ai/src), a sibling is "./x" and frontend/src is "../../frontend/src/x".
    const outside = testTs.filter(
      (path) =>
        !path.startsWith("./") && !path.startsWith("../../frontend/src/"),
    );
    expect(outside).toEqual([]);
  });
});
