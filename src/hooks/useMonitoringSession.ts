import { useCallback, useEffect, useState } from "react";

interface UseMonitoringSessionOptions {
  deltaT: number;
  onTick: () => void;
}

export function useMonitoringSession({
  deltaT,
  onTick,
}: UseMonitoringSessionOptions) {
  const [isMonitoring, setIsMonitoring] = useState(false);

  useEffect(() => {
    if (!isMonitoring) return undefined;
    const interval = window.setInterval(onTick, deltaT * 1000);
    return () => window.clearInterval(interval);
  }, [deltaT, isMonitoring, onTick]);

  const start = useCallback(() => setIsMonitoring(true), []);
  const pause = useCallback(() => setIsMonitoring(false), []);

  return { isMonitoring, start, pause };
}
