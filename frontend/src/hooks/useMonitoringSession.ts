import { useCallback, useEffect, useRef, useState } from "react";

interface UseMonitoringSessionOptions {
  deltaT: number;
  onTick: () => void;
}

export function useMonitoringSession({
  deltaT,
  onTick,
}: UseMonitoringSessionOptions) {
  const [isMonitoring, setIsMonitoring] = useState(false);
  const tickRef = useRef(onTick);

  useEffect(() => {
    tickRef.current = onTick;
  }, [onTick]);

  useEffect(() => {
    if (!isMonitoring) return undefined;
    const interval = window.setInterval(() => tickRef.current(), deltaT * 1000);
    return () => window.clearInterval(interval);
  }, [deltaT, isMonitoring]);

  const start = useCallback(() => setIsMonitoring(true), []);
  const pause = useCallback(() => setIsMonitoring(false), []);

  return { isMonitoring, start, pause };
}
