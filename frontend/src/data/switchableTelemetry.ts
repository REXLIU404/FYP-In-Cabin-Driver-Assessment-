import type { TelemetrySource } from "../../../ai/src/liveLoop";

/**
 * One telemetry source the live loop can hold for a whole session, but which is
 * never a source itself: every call is forwarded to whatever source the getter
 * returns AT THAT MOMENT (plan Task 6). Switching the data mode swaps the source
 * behind the loop - a source that cached the first one would keep feeding the
 * prepared replay into a constructed scenario session, or vice versa.
 */
export const createSwitchableTelemetry = (
  current: () => TelemetrySource,
): TelemetrySource => ({
  reset: (nowMs) => current().reset(nowMs),
  pause: (nowMs) => current().pause(nowMs),
  resume: (nowMs) => current().resume(nowMs),
  read: (nowMs) => current().read(nowMs),
});
