/**
 * Per-window latency bookkeeping for the Live loop (plan Task 10, R4; groundwork for
 * PERF-01). Pure module: no React, no DOM, no clock of its own.
 *
 * Three client-side segments are recorded for every window the server answered:
 *
 *   captureToSendMs  the frame was captured (the tick began, just before the camera was
 *                    sampled) -> the delivery that succeeded was issued. For a window that
 *                    needed a retry this includes the backoff: the retried frame really was
 *                    that old when it finally went out, and `attemptIndex` says so.
 *   networkMs        request issued -> response received and parsed. It contains the whole
 *                    server stay (see `Server-Timing` on the response for its stages) plus
 *                    transport and JSON decoding.
 *   renderMs         response received -> the window has been committed to the UI (a React
 *                    effect after the commit; first paint is NOT included). `null` until
 *                    that happens.
 *
 * All values are wall-clock differences taken from the loop's injected `now()`
 * (`Date.now()` in the browser): 1 ms resolution, not monotonic. A clock that steps
 * backwards inside one window would give a negative difference; it is clamped to 0
 * rather than reported.
 *
 * Entries live in a fixed-capacity ring (`TIMING_CAPACITY` windows): the oldest is dropped
 * when a new one arrives, so a long session cannot grow it. This module only measures; it
 * asserts no budget and draws no performance conclusion.
 */

import type { TimingRecorder, WindowTiming } from "./liveLoop";

export const TIMING_CAPACITY = 500;

/** The three absolute moments the loop observes for one delivery, in epoch milliseconds. */
export interface DeliveryMoments {
  capturedAtMs: number;
  sentAtMs: number;
  receivedAtMs: number;
}

const nonNegative = (ms: number) => Math.max(0, ms);

/** The three client segments from the absolute moments; `renderMs` is `null` until rendered. */
export function segmentsOf(
  moments: DeliveryMoments,
  renderedAtMs: number | null = null,
): { captureToSendMs: number; networkMs: number; renderMs: number | null } {
  return {
    captureToSendMs: nonNegative(moments.sentAtMs - moments.capturedAtMs),
    networkMs: nonNegative(moments.receivedAtMs - moments.sentAtMs),
    renderMs:
      renderedAtMs === null
        ? null
        : nonNegative(renderedAtMs - moments.receivedAtMs),
  };
}

/**
 * Parse a `Server-Timing` header value into `{ name: dur }` (milliseconds).
 *
 * Metrics are comma separated, parameters semicolon separated; a quoted `desc` may itself
 * contain commas and semicolons. A metric without a numeric `dur` is ignored. A name that
 * appears more than once is summed (the header allows repeats and the sum is the time
 * attributable to that name). Returns `null` for an absent, empty or wholly unusable header.
 */
export function parseServerTiming(
  header: string | null | undefined,
): Record<string, number> | null {
  if (!header) return null;
  const out: Record<string, number> = {};
  for (const metric of splitOutsideQuotes(header, ",")) {
    const [name, ...params] = splitOutsideQuotes(metric, ";").map((part) =>
      part.trim(),
    );
    if (!name) continue;
    const dur = params
      .map((param) => /^dur\s*=\s*(.+)$/i.exec(param)?.[1])
      .find((value) => value !== undefined);
    if (dur === undefined) continue;
    const ms = Number(dur.replace(/^"|"$/g, ""));
    if (!Number.isFinite(ms)) continue;
    out[name] = (out[name] ?? 0) + ms;
  }
  return Object.keys(out).length > 0 ? out : null;
}

function splitOutsideQuotes(text: string, separator: string): string[] {
  const parts: string[] = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "\\" && quoted && i + 1 < text.length) {
      current += ch + text[++i];
    } else if (ch === '"') {
      quoted = !quoted;
      current += ch;
    } else if (ch === separator && !quoted) {
      parts.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  parts.push(current);
  return parts;
}

/** The bounded `TimingRecorder` the Live hook injects into the loop. */
export interface TimingBuffer extends TimingRecorder {
  readonly capacity: number;
  readonly size: number;
  /** Oldest to newest. A fresh array; the entries are frozen. */
  snapshot(): WindowTiming[];
}

export function createTimingBuffer(capacity = TIMING_CAPACITY): TimingBuffer {
  if (!Number.isInteger(capacity) || capacity < 1)
    throw new RangeError(
      `capacity must be a positive integer, got ${capacity}`,
    );
  const slots: Array<WindowTiming | undefined> = new Array(capacity);
  let next = 0; // slot the next new entry goes into
  let size = 0;

  // Indices from newest to oldest.
  const newestFirst = function* () {
    for (let n = 1; n <= size; n++) yield (next - n + capacity) % capacity;
  };
  const find = (
    sessionId: string,
    windowId: number,
    unrenderedOnly: boolean,
  ) => {
    for (const index of newestFirst()) {
      const entry = slots[index]!;
      if (
        entry.sessionId === sessionId &&
        entry.windowId === windowId &&
        (!unrenderedOnly || entry.renderedAtMs === null)
      )
        return index;
    }
    return -1;
  };

  return {
    capacity,
    get size() {
      return size;
    },
    push(input) {
      const { serverTiming, ...rest } = input;
      const entry: WindowTiming = Object.freeze({
        ...rest,
        ...segmentsOf(rest),
        renderedAtMs: null,
        renderMs: null,
        server: parseServerTiming(serverTiming),
      });
      const existing = find(input.sessionId, input.windowId, false);
      if (existing !== -1) {
        slots[existing] = entry;
        return;
      }
      slots[next] = entry; // overwrites the oldest once the ring is full
      next = (next + 1) % capacity;
      size = Math.min(size + 1, capacity);
    },
    markRendered(sessionId, windowId, renderedAtMs) {
      const index = find(sessionId, windowId, true);
      if (index === -1) return false;
      const entry = slots[index]!;
      slots[index] = Object.freeze({
        ...entry,
        renderedAtMs,
        renderMs: segmentsOf(entry, renderedAtMs).renderMs,
      });
      return true;
    },
    snapshot() {
      const out: WindowTiming[] = [];
      for (let n = size; n >= 1; n--)
        out.push(slots[(next - n + capacity) % capacity]!);
      return out;
    },
  };
}
