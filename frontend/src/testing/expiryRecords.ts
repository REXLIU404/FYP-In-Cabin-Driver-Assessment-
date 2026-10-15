// Test-only: the records the branch-status rendering tests need, built through the
// REAL producer (`makeRecord` -> `buildRiskUpdate`) with the four provenance
// expiry fields a ruling-A record carries. Nothing in the app imports this file.
//
// Every scenario uses a DIFFERENT age per branch (4 s for vision, 7.5 s for
// telemetry), so a test can tell which branch's expiry reached which place on the
// page: a vision/telemetry swap shows up as the wrong number, not as a pass.
import type { RiskUpdate } from "../types";
import { makeRecord } from "./records";

export const expiryRecords = {
  /** Vision had evidence 4 s old (expired); telemetry is fresh. */
  visionExpired: (): RiskUpdate =>
    makeRecord("missing", "fresh", 1, {
      expiry: {
        vision_expired: true,
        vision_age_s: 4,
        telemetry_expired: false,
        telemetry_age_s: 1.5,
      },
    }),
  /** Telemetry had evidence 7.5 s old (expired); vision is fresh. */
  telemetryExpired: (): RiskUpdate =>
    makeRecord("fresh", "missing", 1, {
      expiry: {
        vision_expired: false,
        vision_age_s: 1.5,
        telemetry_expired: true,
        telemetry_age_s: 7.5,
      },
    }),
  /** Both branches expired: no usable evidence, so no assessment. */
  bothExpired: (): RiskUpdate =>
    makeRecord("missing", "missing", 1, {
      expiry: {
        vision_expired: true,
        vision_age_s: 4,
        telemetry_expired: true,
        telemetry_age_s: 7.5,
      },
    }),
  /** Vision never arrived (missing, NOT expired - no age); telemetry is fresh. */
  visionNeverArrived: (): RiskUpdate =>
    makeRecord("missing", "fresh", 1, {
      expiry: {
        vision_expired: false,
        vision_age_s: null,
        telemetry_expired: false,
        telemetry_age_s: 1.5,
      },
    }),
  /** Both branches fresh. */
  allFresh: (): RiskUpdate => makeRecord("fresh", "fresh", 1),
  /**
   * A record written BEFORE ruling A: vision was stored as `stale` and there are no
   * expiry fields in its provenance at all. It must keep reading and rendering.
   */
  legacyStale: (): RiskUpdate => ({
    ...makeRecord("stale", "fresh", 1),
    provenance: undefined,
  }),
};
