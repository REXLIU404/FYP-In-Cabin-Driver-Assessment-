import { describe, expect, it } from "vitest";

import { createTimingBuffer } from "../../../ai/src/liveTiming";
// Source text of the hook. `?raw` is resolved by Vite at test time, so no
// filesystem API (and no @types/node) is needed - the same approach as
// ai/src/availability.test.ts takes for the export guards.
import hookSource from "./useLiveSession.ts?raw";

// WHY A SOURCE GUARD. The Live loop records per-window timings only when it is
// handed a recorder (`LiveLoopDeps.timings`, injected so that liveLoop.ts keeps its
// one-import range guard). The hook is the only production place that injects it,
// and the repository has no DOM environment to render the hook in. Without this
// guard a refactor could drop the injection, or make the buffer unbounded, and every
// other test would stay green: Part 2's PERF-01 would then find an empty or an
// unbounded buffer. The pure pieces (the ring, the segments, the loop recording into
// it) are covered by liveTiming.test.ts and liveLoopTiming.test.ts; this file pins
// the one thing they cannot see - that the production hook uses them.

// A string literal, or a comment. Strings are matched first, so a `//` inside a
// string (a URL) is not taken for a comment.
const STRING_OR_COMMENT =
  /("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)|\/\*[\s\S]*?\*\/|\/\/[^\n]*/g;

/** The source with every comment blanked, so commented-out code cannot satisfy a check. */
function withoutComments(source: string): string {
  return source.replace(STRING_OR_COMMENT, (match, literal?: string) =>
    literal === undefined ? " " : match,
  );
}

/** Index of the closing quote of the string literal that opens at `open`. */
function endOfString(code: string, open: number): number {
  for (let i = open + 1; i < code.length; i++) {
    if (code[i] === "\\") i++;
    else if (code[i] === code[open]) return i;
  }
  return code.length;
}

const isQuote = (ch: string) => ch === '"' || ch === "'" || ch === "`";

/** How many brackets are open at `index`; brackets inside string literals do not count. */
function depthAt(code: string, index: number): number {
  let depth = 0;
  for (let i = 0; i < index; i++) {
    const ch = code[i];
    if (isQuote(ch)) i = endOfString(code, i);
    else if ("([{".includes(ch)) depth++;
    else if (")]}".includes(ch)) depth--;
  }
  return depth;
}

/** The text between the parentheses of the first call to `callee`, or null. */
function argumentsOf(code: string, callee: string): string | null {
  const call = new RegExp(`\\b${callee}\\s*(?:<[^<>()]*>)?\\s*\\(`).exec(code);
  if (!call) return null;
  const open = call.index + call[0].length - 1;
  let depth = 0;
  for (let i = open; i < code.length; i++) {
    const ch = code[i];
    if (isQuote(ch)) i = endOfString(code, i);
    else if ("([{".includes(ch)) depth++;
    else if (")]}".includes(ch) && --depth === 0)
      return code.slice(open + 1, i);
  }
  return null;
}

type Requirement =
  | "IMPORT"
  | "ONE_BUFFER"
  | "PER_INSTANCE"
  | "OPTION"
  | "SINGLE_OPTION"
  | "ACCESSOR"
  | "CLEANUP"
  | "RENDERED";

/** The requirements the hook's source fails; an empty list is a pass. */
function violations(source: string): Requirement[] {
  const code = withoutComments(source);
  const args = argumentsOf(code, "createLiveLoop") ?? "";
  const bufferOption =
    /\btimings\s*:\s*createTimingBuffer\(\s*\)\s*(?=,|\}|$)/.exec(args);
  const accessor =
    /Object\.defineProperty\(\s*host\s*,\s*"__draLiveTimings"\s*,\s*\{([^{}]*)\}\s*\)/.exec(
      code,
    );
  const checks: Array<[Requirement, boolean]> = [
    // The buffer comes from the shared, tested module - not a local stand-in.
    [
      "IMPORT",
      /import\s*\{\s*createTimingBuffer\s*\}\s*from\s*"\.\.\/\.\.\/\.\.\/ai\/src\/liveTiming"\s*;/.test(
        code,
      ),
    ],
    // The import and exactly one call: no second, shared or module-level buffer.
    ["ONE_BUFFER", (code.match(/\bcreateTimingBuffer\b/g) ?? []).length === 2],
    // The loop (and so its buffer) is made once per hook instance.
    [
      "PER_INSTANCE",
      /useState\(\s*\(\)\s*=>\s*createLiveLoop\s*(?:<[^<>()]*>)?\s*\(/.test(
        code,
      ),
    ],
    // The argument-free call is the default 500-window ring (pinned below); any
    // argument, wrapper or fallback is a different - possibly unbounded - buffer.
    [
      "OPTION",
      bufferOption !== null && depthAt(args, bufferOption.index) === 1,
    ],
    ["SINGLE_OPTION", (args.match(/\btimings\s*:/g) ?? []).length === 1],
    // `window.__draLiveTimings` is a getter over the loop's buffer: a fresh copy per read.
    [
      "ACCESSOR",
      /const\s+host\s*=\s*window\b/.test(code) &&
        accessor !== null &&
        /(?:^|[\s,])get\s*:\s*\(\s*\)\s*=>\s*loop\.getTimings\(\s*\)\s*(?:,|$)/.test(
          accessor[1],
        ) &&
        !/\bvalue\s*:/.test(accessor[1]),
    ],
    [
      "CLEANUP",
      /return\s*\(\s*\)\s*=>\s*\{\s*delete\s+host\.__draLiveTimings\s*;?\s*\}/.test(
        code,
      ),
    ],
    // `renderMs` is closed for the newest window once React has committed it.
    [
      "RENDERED",
      /const\s+newestWindowId\s*=\s*live\.history\.length\s*>\s*0\s*\?\s*live\.history\[\s*live\.history\.length\s*-\s*1\s*\]\.window_id\s*:\s*null\s*;/.test(
        code,
      ) &&
        /useEffect\(\s*\(\)\s*=>\s*\{\s*if\s*\(\s*newestWindowId\s*!==\s*null\s*\)\s*loop\.markRendered\(\s*newestWindowId\s*\)\s*;?\s*\}\s*,\s*\[\s*loop\s*,\s*newestWindowId\s*\]\s*,?\s*\)/.test(
          code,
        ),
    ],
  ];
  return checks.filter(([, ok]) => !ok).map(([name]) => name);
}

describe("useLiveSession: the production Live loop records into a bounded buffer", () => {
  it("the hook's source meets every wiring requirement", () => {
    expect(violations(hookSource)).toEqual([]);
  });

  it("the argument-free createTimingBuffer() it uses is the 500-window ring", () => {
    expect(createTimingBuffer().capacity).toBe(500);
    const buffer = createTimingBuffer();
    for (let windowId = 1; windowId <= 501; windowId++)
      buffer.push({
        sessionId: "s1",
        windowId,
        requestId: `req-${windowId}`,
        attemptIndex: 1,
        capturedAtMs: 1000,
        sentAtMs: 1010,
        receivedAtMs: 1100,
      });
    expect(buffer.size).toBe(500);
    expect(buffer.snapshot()[0].windowId).toBe(2);
  });
});

// The guard has to fail on the regressions it exists for. Each mutant below edits
// the REAL hook source in memory (exactly one occurrence of the edited text, so a
// drifted source fails loudly instead of testing nothing) and must break the named
// requirement. The first two are the unbounded and the "records nothing" mutants a
// reviewer ran against the unguarded hook: both used to leave every test green.
const once = (source: string, from: string, to: string): string => {
  expect(source.split(from), `"${from}" must occur exactly once`).toHaveLength(
    2,
  );
  return source.replace(from, () => to);
};

const MUTANTS: Array<{
  name: string;
  edit: (source: string) => string;
  breaks: Requirement;
}> = [
  {
    name: "an effectively unbounded buffer: createTimingBuffer(10_000_000)",
    edit: (s) =>
      once(
        s,
        "timings: createTimingBuffer(),",
        "timings: createTimingBuffer(10_000_000),",
      ),
    breaks: "OPTION",
  },
  {
    name: "a recorder that is never injected: createTimingBuffer() && undefined",
    edit: (s) =>
      once(
        s,
        "timings: createTimingBuffer(),",
        "timings: createTimingBuffer() && undefined,",
      ),
    breaks: "OPTION",
  },
  {
    name: "the injection dropped altogether",
    edit: (s) => once(s, "timings: createTimingBuffer(),", ""),
    breaks: "OPTION",
  },
  {
    name: "the injection commented out",
    edit: (s) =>
      once(
        s,
        "timings: createTimingBuffer(),",
        "// timings: createTimingBuffer(),",
      ),
    breaks: "OPTION",
  },
  {
    name: "the injection moved into a nested object the loop never reads",
    edit: (s) =>
      once(
        s,
        "timings: createTimingBuffer(),",
        "unused: { timings: createTimingBuffer() },",
      ),
    breaks: "OPTION",
  },
  {
    name: "a module-level buffer shared by every hook instance",
    edit: (s) =>
      once(
        once(s, "timings: createTimingBuffer(),", "timings: SHARED,"),
        "export function useLiveSession(",
        "const SHARED = createTimingBuffer();\nexport function useLiveSession(",
      ),
    breaks: "OPTION",
  },
  {
    name: "a later duplicate option that overrides the buffer",
    edit: (s) =>
      once(
        s,
        "timings: createTimingBuffer(),",
        "timings: createTimingBuffer(), timings: undefined,",
      ),
    breaks: "SINGLE_OPTION",
  },
  {
    name: "a local stand-in for the shared createTimingBuffer",
    edit: (s) =>
      once(
        s,
        'import { createTimingBuffer } from "../../../ai/src/liveTiming";',
        "const createTimingBuffer = () => ({}) as never;",
      ),
    breaks: "IMPORT",
  },
  {
    name: "the accessor publishes a one-off value, not a getter",
    edit: (s) =>
      once(s, "get: () => loop.getTimings(),", "value: loop.getTimings(),"),
    breaks: "ACCESSOR",
  },
  {
    name: "the accessor getter returns an empty list",
    edit: (s) => once(s, "get: () => loop.getTimings(),", "get: () => [],"),
    breaks: "ACCESSOR",
  },
  {
    name: "the accessor getter returns only part of the buffer",
    edit: (s) =>
      once(
        s,
        "get: () => loop.getTimings(),",
        "get: () => loop.getTimings().slice(-1),",
      ),
    breaks: "ACCESSOR",
  },
  {
    name: "the accessor is attached to an object other than window",
    edit: (s) =>
      once(s, "const host = window as unknown", "const host = {} as unknown"),
    breaks: "ACCESSOR",
  },
  {
    name: "the accessor is left behind after unmount",
    edit: (s) => once(s, "delete host.__draLiveTimings;", ""),
    breaks: "CLEANUP",
  },
  {
    name: "the render effect runs once instead of on every new window",
    edit: (s) => once(s, "[loop, newestWindowId]", "[loop]"),
    breaks: "RENDERED",
  },
  {
    name: "the render effect never calls markRendered",
    edit: (s) =>
      once(
        s,
        "if (newestWindowId !== null) loop.markRendered(newestWindowId);",
        "void newestWindowId;",
      ),
    breaks: "RENDERED",
  },
  {
    name: "the render effect follows the oldest window, not the newest",
    edit: (s) =>
      once(
        s,
        "live.history[live.history.length - 1].window_id",
        "live.history[0].window_id",
      ),
    breaks: "RENDERED",
  },
];

describe("the wiring guard fails on the regressions it exists for", () => {
  it.each(MUTANTS)("$name", ({ edit, breaks }) => {
    const mutant = edit(hookSource);
    expect(mutant).not.toBe(hookSource);
    expect(violations(mutant)).toContain(breaks);
  });
});

describe("the guard's own helpers", () => {
  it("withoutComments drops line and block comments but keeps string literals", () => {
    const code = withoutComments(
      "a // timings: createTimingBuffer()\n/* timings: createTimingBuffer() */ b \"// kept\" '/* kept */'",
    );
    expect(code).not.toContain("createTimingBuffer");
    expect(code).toContain('"// kept"');
    expect(code).toContain("'/* kept */'");
  });

  it("depthAt counts open brackets and ignores brackets inside strings", () => {
    const code = 'f({ a: g(1), b: { c: 2 }, s: "{(" })';
    expect(depthAt(code, code.indexOf("a:"))).toBe(2);
    expect(depthAt(code, code.indexOf("1"))).toBe(3);
    expect(depthAt(code, code.indexOf("c:"))).toBe(3);
    expect(depthAt(code, code.indexOf("s:"))).toBe(2);
    expect(depthAt(code, code.length)).toBe(0);
  });

  it("argumentsOf returns the call's argument text, past generics and strings", () => {
    expect(
      argumentsOf('x(1); make<T>({ a: ")", b: f(2) }); y(3)', "make"),
    ).toBe('{ a: ")", b: f(2) }');
    expect(argumentsOf("nothing here", "make")).toBeNull();
  });
});
