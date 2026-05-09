import type { AppConfig, RiskUpdate, SessionMeta } from "../types";
import { DEFAULT_CONFIG } from "./riskLogic";

const SESSION_INDEX_KEY = "session_index";
const ACTIVE_SESSION_KEY = "active_session";
const APP_CONFIG_KEY = "app_config";
const sessionKey = (sessionId: string) => `session_log:${sessionId}`;

const canUseStorage = () =>
  typeof window !== "undefined" && Boolean(window.localStorage);

const readJson = <T>(key: string, fallback: T): T => {
  if (!canUseStorage()) return fallback;
  try {
    const value = window.localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
};

const writeJson = (key: string, value: unknown) => {
  if (!canUseStorage()) return;
  window.localStorage.setItem(key, JSON.stringify(value));
};

export const loadSessionLog = (sessionId: string): RiskUpdate[] =>
  readJson<RiskUpdate[]>(sessionKey(sessionId), []);

export const appendRecord = (sessionId: string, record: RiskUpdate) => {
  const log = loadSessionLog(sessionId);
  writeJson(sessionKey(sessionId), [...log, record]);
  upsertSessionMeta(sessionId, log.length + 1);
};

export const flagWindow = (
  sessionId: string,
  windowId: number,
  flagged: boolean,
) => {
  const log = loadSessionLog(sessionId).map((record) =>
    record.window_id === windowId ? { ...record, flagged } : record,
  );
  writeJson(sessionKey(sessionId), log);
  upsertSessionMeta(sessionId, log.length);
};

export const clearSession = (sessionId: string) => {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(sessionKey(sessionId));
  const index = listSessions().filter((session) => session.id !== sessionId);
  writeJson(SESSION_INDEX_KEY, index);
};

export const listSessions = (): SessionMeta[] =>
  readJson<SessionMeta[]>(SESSION_INDEX_KEY, []);

export const setActiveSession = (sessionId: string) => {
  if (!canUseStorage()) return;
  window.localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
};

export const loadActiveSession = () =>
  canUseStorage() ? window.localStorage.getItem(ACTIVE_SESSION_KEY) : null;

export const loadConfig = (): AppConfig => {
  const saved = readJson<Partial<AppConfig> & { showExplanation?: boolean }>(
    APP_CONFIG_KEY,
    {},
  );
  const merged = { ...DEFAULT_CONFIG, ...saved };
  const operationMode =
    saved.operationMode === DEFAULT_CONFIG.operationMode
      ? saved.operationMode
      : DEFAULT_CONFIG.operationMode;
  const enableEvidenceInterpretation =
    typeof saved.enableEvidenceInterpretation === "boolean"
      ? saved.enableEvidenceInterpretation
      : (saved.showExplanation ?? DEFAULT_CONFIG.enableEvidenceInterpretation);

  return {
    ...merged,
    operationMode,
    enableEvidenceInterpretation,
    thresholdLow:
      merged.thresholdLow <= 1
        ? merged.thresholdLow * 100
        : merged.thresholdLow,
    thresholdHigh:
      merged.thresholdHigh <= 1
        ? merged.thresholdHigh * 100
        : merged.thresholdHigh,
  };
};

export const saveConfig = (config: AppConfig) =>
  writeJson(APP_CONFIG_KEY, config);

const upsertSessionMeta = (sessionId: string, totalWindows: number) => {
  const index = listSessions();
  const existing = index.find((session) => session.id === sessionId);
  const next: SessionMeta = {
    id: sessionId,
    created_at: existing?.created_at ?? new Date().toISOString(),
    total_windows: totalWindows,
  };
  writeJson(SESSION_INDEX_KEY, [
    next,
    ...index.filter((session) => session.id !== sessionId),
  ]);
  setActiveSession(sessionId);
};
