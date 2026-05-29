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
    ["Speed", `${telemetry.speed_kmph.toFixed(1)} km/h`],
    ["Accel X", `${telemetry.accel_x.toFixed(2)} m/s2`],
    ["Accel Y", `${telemetry.accel_y.toFixed(2)} m/s2`],
    ["Brake pressure", telemetry.brake_pressure.toFixed(1)],
    ["Steering", `${telemetry.steering_angle.toFixed(1)} deg`],
    ["Throttle", telemetry.throttle.toFixed(1)],
    ["Lane deviation", telemetry.lane_deviation.toFixed(2)],
    ["Headway", `${telemetry.headway_distance.toFixed(1)} m`],
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
