import type { AlertSeverity, RiskLevel } from "./types";

/**
 * AlertSeverity finite-state machine (wall-clock, anti-flicker).
 *
 * This is the "Alert State Manager" of the architecture. It is deliberately
 * separate from the per-window severity mapping in riskLogic: that mapping is
 * the *instantaneous* severity, whereas this FSM applies temporal hysteresis so
 * the operator-facing alert does not flicker on momentary spikes.
 *
 * Rules:
 *  - Escalate to HIGH_ALERT only after RiskLevel has stayed High for >= sustainMs.
 *  - Auto-recover to NORMAL only after RiskLevel has stayed Low for >= recoverMs.
 *  - Medium maps to CAUTION (genuine, immediate).
 *  - A window with NO assessment (`level === null`) suspends the timers and
 *    leaves the held severity alone: the dead interval is credited towards
 *    neither the sustain nor the recovery, and an active alert is neither
 *    escalated nor cleared by missing evidence. Mirrors `_step_alert_fsm` in
 *    backend/app/inference.py.
 *
 * `AlertFsmState.severity` is never null; nullability exists only at the emitted
 * RiskUpdate boundary, where the caller must emit `AlertSeverity: null` for a
 * window whose `RiskLevel` is null instead of copying `severity` onto it.
 */

export const ALERT_SUSTAIN_MS = 2000; // High must persist >= 2s before HIGH_ALERT
export const ALERT_RECOVER_MS = 10000; // Low must persist >= 10s before NORMAL

export interface AlertFsmState {
  severity: AlertSeverity;
  highSince: number | null; // wall-clock ms when the current High streak began
  lowSince: number | null; // wall-clock ms when the current Low streak began
}

export interface AlertFsmOptions {
  sustainMs?: number;
  recoverMs?: number;
}

export const initAlertState = (): AlertFsmState => ({
  severity: "NORMAL",
  highSince: null,
  lowSince: null,
});

export const updateAlertState = (
  prev: AlertFsmState,
  level: RiskLevel | null,
  now: number,
  options: AlertFsmOptions = {},
): AlertFsmState => {
  const sustainMs = options.sustainMs ?? ALERT_SUSTAIN_MS;
  const recoverMs = options.recoverMs ?? ALERT_RECOVER_MS;

  if (level === null) {
    // Suspend, not freeze: dropping both streaks means the first assessed
    // window afterwards re-anchors them to itself, so the interruption is
    // credited toward neither timer. Without this branch a null level would
    // fall through to the Low branch below and start the recovery timer.
    return { severity: prev.severity, highSince: null, lowSince: null };
  }

  if (level === "High") {
    const highSince = prev.highSince ?? now;
    const sustained = now - highSince >= sustainMs;
    const severity: AlertSeverity =
      sustained || prev.severity === "HIGH_ALERT" ? "HIGH_ALERT" : "CAUTION";
    return { severity, highSince, lowSince: null };
  }

  if (level === "Medium") {
    // Genuine caution; clears any High streak, not yet in a recovery window.
    return { severity: "CAUTION", highSince: null, lowSince: null };
  }

  // level === "Low": hold the current (possibly elevated) severity until Low
  // has persisted for >= recoverMs, then recover to NORMAL (anti-flicker).
  const lowSince = prev.lowSince ?? now;
  const recovered = now - lowSince >= recoverMs;
  const severity: AlertSeverity = recovered ? "NORMAL" : prev.severity;
  return { severity, highSince: null, lowSince };
};
