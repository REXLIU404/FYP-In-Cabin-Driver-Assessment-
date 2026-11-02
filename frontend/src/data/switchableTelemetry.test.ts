import { describe, expect, it, vi } from "vitest";

import type { TelemetrySource } from "../../../ai/src/liveLoop";
import { createSwitchableTelemetry } from "./switchableTelemetry";

/**
 * Task 6 (constructed scenario) - the switchable telemetry source. The live loop
 * receives ONE source for the whole session; switching the data mode must not tear
 * the loop down, so the source forwards every call to whatever source the getter
 * returns AT THE MOMENT of the call. A source that cached the first one would keep
 * feeding prepared replay telemetry into a constructed scenario session.
 */
type Spy = ReturnType<typeof vi.fn>;
const spySource = (
  name: string,
): TelemetrySource & { reset: Spy; pause: Spy; resume: Spy; read: Spy } => {
  const source = {
    reset: vi.fn(() => `${name}.reset`),
    pause: vi.fn(() => `${name}.pause`),
    resume: vi.fn(() => `${name}.resume`),
    read: vi.fn(() => `${name}.read`),
  };
  return source as unknown as TelemetrySource & {
    reset: Spy;
    pause: Spy;
    resume: Spy;
    read: Spy;
  };
};

describe("createSwitchableTelemetry", () => {
  it("forwards every call to the source the getter returns right now", () => {
    const prepared = spySource("prepared");
    const current: TelemetrySource = prepared;
    const switchable = createSwitchableTelemetry(() => current);

    expect(switchable.reset(10)).toBe("prepared.reset");
    expect(switchable.pause(20)).toBe("prepared.pause");
    expect(switchable.read(30)).toBe("prepared.read");
    expect(switchable.resume(40)).toBe("prepared.resume");
    expect(prepared.reset).toHaveBeenCalledWith(10);
    expect(prepared.pause).toHaveBeenCalledWith(20);
    expect(prepared.read).toHaveBeenCalledWith(30);
    expect(prepared.resume).toHaveBeenCalledWith(40);
  });

  it("calls made after a switch land on the new source", () => {
    const prepared = spySource("prepared");
    const scenario = spySource("scenario");
    let current: TelemetrySource = prepared;
    const switchable = createSwitchableTelemetry(() => current);

    switchable.reset(0);
    current = scenario;
    switchable.read(100);
    switchable.pause(200);
    switchable.resume(300);
    switchable.read(400);

    expect(prepared.reset).toHaveBeenCalledTimes(1);
    expect(prepared.read).not.toHaveBeenCalled();
    expect(scenario.read).toHaveBeenNthCalledWith(1, 100);
    expect(scenario.pause).toHaveBeenCalledWith(200);
    expect(scenario.resume).toHaveBeenCalledWith(300);
    expect(scenario.read).toHaveBeenNthCalledWith(2, 400);
  });

  it("re-resolves the source on every call, not once per tick", () => {
    const first = spySource("first");
    const second = spySource("second");
    let current: TelemetrySource = first;
    const switchable = createSwitchableTelemetry(() => current);

    switchable.read(0);
    current = second;
    switchable.read(1);
    current = first;
    switchable.read(2);

    expect(first.read).toHaveBeenCalledTimes(2);
    expect(second.read).toHaveBeenCalledTimes(1);
  });
});
