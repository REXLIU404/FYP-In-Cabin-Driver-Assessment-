import type { TelemetryFeatures } from "../types";

interface TelemetrySummaryProps {
  telemetry: TelemetryFeatures | null;
}

export function TelemetrySummary({ telemetry }: TelemetrySummaryProps) {
  if (!telemetry) {
    return (
      <div className="empty-state">
        Telemetry record unavailable for this window.
      </div>
    );
  }

  const rows = [
    ["Speed", `${telemetry.speed} km/h`],
    ["Acceleration", `${telemetry.acceleration.toFixed(1)} m/s2`],
    ["Steering", `${telemetry.steering_angle.toFixed(1)} deg`],
    ["Brake usage", telemetry.brake_usage.toFixed(2)],
    ["Lane deviation", telemetry.lane_deviation.toFixed(2)],
  ];

  return (
    <div className="telemetry-grid">
      {rows.map(([label, value]) => (
        <div className="telemetry-cell" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
