import type { SessionMeta } from "../types";

export interface EndSessionAvailability {
  liveLike: boolean;
  hasSession: boolean;
  busy: boolean;
  retrying: boolean;
  ending: boolean;
  ended: boolean;
}

export const canEndSession = (state: EndSessionAvailability): boolean =>
  state.liveLike &&
  state.hasSession &&
  !state.busy &&
  !state.retrying &&
  !state.ending &&
  !state.ended;

export const savedSessionLabel = (session: SessionMeta): string =>
  `${session.id} · ${session.total_windows} windows${
    session.status === "CLOSED" ? " · CLOSED" : ""
  }`;
