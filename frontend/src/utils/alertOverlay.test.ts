import { describe, expect, it } from "vitest";

import { assertAvailabilityInvariant } from "../../../ai/src/availability";
import { initAlertState } from "../../../ai/src/alertFsm";
import { makeRecord } from "../testing/records";
import { applyAlertState } from "./alertOverlay";

// Hard-coded on purpose (see global constraints): 2000 ms to HIGH_ALERT.
const HIGH = { P_distraction: 0.95, P_telemetry_anomaly: 0.95 } as const;

describe("applyAlertState: the FSM overlay must not overwrite a null AlertSeverity", () => {
  it("an unavailable record keeps AlertSeverity null even when the FSM holds a severity", () => {
    // Drive the FSM into HIGH_ALERT first, so a naive spread would write it.
    let state = initAlertState();
    state = applyAlertState(
      makeRecord("fresh", "fresh", 1, HIGH),
      state,
      0,
    ).state;
    state = applyAlertState(
      makeRecord("fresh", "fresh", 2, HIGH),
      state,
      2500,
    ).state;
    expect(state.severity).toBe("HIGH_ALERT");

    const unavailable = makeRecord("missing", "missing", 3);
    expect(unavailable.RiskLevel).toBeNull();
    const result = applyAlertState(unavailable, state, 3000);

    expect(result.record.AlertSeverity).toBeNull();
    // ...but the FSM memory survives, so recovery is not reset by a blackout.
    expect(result.state.severity).toBe("HIGH_ALERT");
    expect(() => assertAvailabilityInvariant(result.record)).not.toThrow();
  });

  it("the four-fields-null contract holds on the emitted record", () => {
    const { record } = applyAlertState(
      makeRecord("missing", "missing", 1),
      initAlertState(),
      0,
    );
    expect(record).toMatchObject({
      assessment_available: false,
      RiskScore: null,
      RiskLevel: null,
      DominantEvidence: null,
      AlertSeverity: null,
      SystemHealth: "UNAVAILABLE",
    });
  });

  it("an available record still receives the FSM severity (escalation after 2000 ms)", () => {
    let state = initAlertState();
    const first = applyAlertState(
      makeRecord("fresh", "fresh", 1, HIGH),
      state,
      0,
    );
    state = first.state;
    expect(first.record.AlertSeverity).toBe("CAUTION");
    const second = applyAlertState(
      makeRecord("fresh", "fresh", 2, HIGH),
      state,
      2000,
    );
    expect(second.record.AlertSeverity).toBe("HIGH_ALERT");
    expect(() => assertAvailabilityInvariant(second.record)).not.toThrow();
  });
});
