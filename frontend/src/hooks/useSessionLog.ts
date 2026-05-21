import { useCallback, useState } from "react";
import type { RiskUpdate } from "../types";
import {
  appendRecord,
  clearSession,
  flagWindow,
  loadSessionLog,
} from "../utils/persistence";

export function useSessionLog(sessionId: string) {
  const [log, setLog] = useState<RiskUpdate[]>(() => loadSessionLog(sessionId));

  const append = useCallback(
    (record: RiskUpdate) => {
      appendRecord(sessionId, record);
      setLog(loadSessionLog(sessionId));
    },
    [sessionId],
  );

  const flag = useCallback(
    (windowId: number, flagged: boolean) => {
      flagWindow(sessionId, windowId, flagged);
      setLog(loadSessionLog(sessionId));
    },
    [sessionId],
  );

  const reset = useCallback(() => {
    clearSession(sessionId);
    setLog([]);
  }, [sessionId]);

  return { log, append, flag, reset };
}
