import type { TelemetryFeatures } from "../types";
import { Gauge, Activity, Disc, Compass, ArrowLeftRight } from "lucide-react";

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

  // Define mapping for progress bar values
  // Speed: max 120 km/h
  const speedPct = Math.min(100, (telemetry.speed / 120) * 100);
  // Acceleration: max 5 m/s²
  const accelPct = Math.min(100, (Math.abs(telemetry.acceleration) / 5) * 100);
  // Brake: 0.0 to 1.0 -> percentage
  const brakePct = Math.min(100, telemetry.brake_usage * 100);
  // Lane deviation: 0.0 to 1.0 -> percentage
  const lanePct = Math.min(100, telemetry.lane_deviation * 100);
  // Steering angle: center is 0, display scale -30 to +30 deg. Center marker calculation.
  const steeringDeg = telemetry.steering_angle;
  // Left/Right steer percentage offset from center (50%)
  // -30 deg -> 10%, 0 deg -> 50%, +30 deg -> 90%
  const steeringPosition = Math.max(10, Math.min(90, 50 + (steeringDeg / 30) * 40));

  return (
    <div className="telemetry-console">
      {/* Speed Dial */}
      <div className="telemetry-bar-card">
        <div className="telemetry-bar-info">
          <div className="telemetry-bar-label">
            <Gauge size={16} className="telemetry-icon" />
            <span>Vehicle Speed</span>
          </div>
          <strong className={telemetry.speed > 90 ? "text-warning" : ""}>
            {telemetry.speed} <small>km/h</small>
          </strong>
        </div>
        <div className="telemetry-meter-track">
          <div 
            className={`telemetry-meter-fill ${telemetry.speed > 90 ? "bg-warning" : "bg-primary"}`} 
            style={{ width: `${speedPct}%` }} 
          />
        </div>
      </div>

      {/* Acceleration */}
      <div className="telemetry-bar-card">
        <div className="telemetry-bar-info">
          <div className="telemetry-bar-label">
            <Activity size={16} className="telemetry-icon" />
            <span>Acceleration</span>
          </div>
          <strong>
            {telemetry.acceleration.toFixed(1)} <small>m/s²</small>
          </strong>
        </div>
        <div className="telemetry-meter-track">
          <div 
            className="telemetry-meter-fill bg-primary" 
            style={{ width: `${accelPct}%` }} 
          />
        </div>
      </div>

      {/* Steering (Bidirectional Centering Meter) */}
      <div className="telemetry-bar-card">
        <div className="telemetry-bar-info">
          <div className="telemetry-bar-label">
            <Compass size={16} className="telemetry-icon" />
            <span>Steering Angle</span>
          </div>
          <strong>
            {steeringDeg.toFixed(1)}° <small>{steeringDeg > 0 ? "Right" : steeringDeg < 0 ? "Left" : "Center"}</small>
          </strong>
        </div>
        <div className="telemetry-meter-track telemetry-steering-track">
          <div className="steering-center-mark" />
          <div 
            className="steering-pointer" 
            style={{ left: `${steeringPosition}%` }} 
          />
        </div>
      </div>

      {/* Brake Usage */}
      <div className="telemetry-bar-card">
        <div className="telemetry-bar-info">
          <div className="telemetry-bar-label">
            <Disc size={16} className="telemetry-icon" />
            <span>Brake Pressure</span>
          </div>
          <strong>
            {(telemetry.brake_usage * 100).toFixed(0)}%
          </strong>
        </div>
        <div className="telemetry-meter-track">
          <div 
            className={`telemetry-meter-fill ${telemetry.brake_usage > 0.6 ? "bg-danger" : "bg-success"}`} 
            style={{ width: `${brakePct}%` }} 
          />
        </div>
      </div>

      {/* Lane Deviation */}
      <div className="telemetry-bar-card">
        <div className="telemetry-bar-info">
          <div className="telemetry-bar-label">
            <ArrowLeftRight size={16} className="telemetry-icon" />
            <span>Lane Offset</span>
          </div>
          <strong>
            {telemetry.lane_deviation.toFixed(2)}
          </strong>
        </div>
        <div className="telemetry-meter-track">
          <div 
            className={`telemetry-meter-fill ${telemetry.lane_deviation > 0.5 ? "bg-warning" : "bg-primary"}`} 
            style={{ width: `${lanePct}%` }} 
          />
        </div>
      </div>
    </div>
  );
}

