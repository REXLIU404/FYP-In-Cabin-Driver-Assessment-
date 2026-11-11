import { describe, expect, it } from "vitest";

import type { SessionMeta } from "../types";
import { canEndSession, savedSessionLabel } from "./sessionLifecycle";

const idle = {
  liveLike: true,
  hasSession: true,
  busy: false,
  retrying: false,
  ending: false,
  ended: false,
};

describe("canEndSession: the End Session button's enablement", () => {
  it("is enabled only for a current Live session that is not busy, retrying, closing or already ended", () => {
    expect(canEndSession(idle)).toBe(true);
  });

  it.each([
    ["no Live session", { liveLike: false }],
    ["no current session", { hasSession: false }],
    ["setup is busy", { busy: true }],
    ["a manual retry is in flight", { retrying: true }],
    ["the close call is in flight", { ending: true }],
    ["the session has already ended", { ended: true }],
  ])("is disabled when %s", (_reason, change) => {
    expect(canEndSession({ ...idle, ...change })).toBe(false);
  });
});

describe("savedSessionLabel: the saved-session picker labels a closed session", () => {
  const session: SessionMeta = {
    id: "S-live-1",
    created_at: "2026-01-01T12:00:00+00:00",
    total_windows: 12,
    operation_mode: "LIVE_MODEL_RUNTIME",
    status: "CLOSED",
  };

  it("shows the CLOSED status beside the window count", () => {
    expect(savedSessionLabel(session)).toBe("S-live-1 · 12 windows · CLOSED");
  });

  it("does not label an active session as closed", () => {
    expect(savedSessionLabel({ ...session, status: "ACTIVE" })).toBe(
      "S-live-1 · 12 windows",
    );
    expect(savedSessionLabel({ ...session, status: undefined })).toBe(
      "S-live-1 · 12 windows",
    );
  });
});
