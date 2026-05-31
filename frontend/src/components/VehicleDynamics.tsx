import {
  Activity,
  Car,
  CircleGauge,
  Disc3,
  Fuel,
  type LucideIcon,
  MoveHorizontal,
  Navigation,
} from "lucide-react";
import type { TelemetryFeatures } from "../types";

interface VehicleDynamicsProps {
  telemetry: TelemetryFeatures | null;
}

type Tone = "calm" | "watch" | "alert";

interface DynamicsRow {
  key: string;
  icon: LucideIcon;
  label: string;
  value: string;
  note: string;
  fill: number;
  tone: Tone;
}

const clampPercent = (value: number) => Math.min(100, Math.max(0, value));

const toneFor = (ratio: number): Tone => {
  if (ratio >= 0.75) return "alert";
  if (ratio >= 0.45) return "watch";
  return "calm";
};

const buildRows = (telemetry: TelemetryFeatures): DynamicsRow[] => {
  const speedRatio = telemetry.speed_kmph / 140;
  const accelRatio = Math.abs(telemetry.accel_x) / 4;
  const steeringRatio = Math.abs(telemetry.steering_angle) / 45;
  const brakeRatio = telemetry.brake_pressure / 100;
  const throttleRatio = telemetry.throttle / 100;
  const laneRatio = telemetry.lane_deviation / 1.5;
  // Shorter headway = higher risk, so invert for the fill/tone.
  const headwayRisk = clampPercent((1 - telemetry.headway_distance / 40) * 100);

  const steeringSide =
    Math.abs(telemetry.steering_angle) < 1
      ? "centered"
      : telemetry.steering_angle < 0
        ? "left"
        : "right";

  return [
    {
      key: "speed",
      icon: CircleGauge,
      label: "Speed",
      value: `${Math.round(telemetry.speed_kmph)} km/h`,
      note:
        speedRatio >= 0.75 ? "high" : speedRatio >= 0.45 ? "moderate" : "low",
      fill: clampPercent(speedRatio * 100),
      tone: toneFor(speedRatio),
    },
    {
      key: "accel",
      icon: Activity,
      label: "Acceleration",
      value: `${telemetry.accel_x.toFixed(1)} m/s²`,
      note:
        accelRatio >= 0.75
          ? "hard"
          : accelRatio >= 0.45
            ? "firm"
            : "gentle",
      fill: clampPercent(accelRatio * 100),
      tone: toneFor(accelRatio),
    },
    {
      key: "steering",
      icon: Navigation,
      label: "Steering",
      value:
        steeringSide === "centered"
          ? "centered"
          : `${Math.abs(telemetry.steering_angle).toFixed(0)}° ${steeringSide}`,
      note:
        steeringRatio >= 0.75
          ? "sharp"
          : steeringRatio >= 0.45
            ? "turning"
            : "straight",
      fill: clampPercent(steeringRatio * 100),
      tone: toneFor(steeringRatio),
    },
    {
      key: "brake",
      icon: Disc3,
      label: "Braking",
      value: `${Math.round(telemetry.brake_pressure)}%`,
      note:
        brakeRatio >= 0.75 ? "heavy" : brakeRatio >= 0.45 ? "moderate" : "light",
      fill: clampPercent(brakeRatio * 100),
      tone: toneFor(brakeRatio),
    },
    {
      key: "throttle",
      icon: Fuel,
      label: "Throttle",
      value: `${Math.round(telemetry.throttle)}%`,
      note:
        throttleRatio >= 0.75
          ? "heavy"
          : throttleRatio >= 0.45
            ? "steady"
            : "easing",
      fill: clampPercent(throttleRatio * 100),
      tone: toneFor(throttleRatio),
    },
    {
      key: "lane",
      icon: MoveHorizontal,
      label: "Lane position",
      value:
        telemetry.lane_deviation < 0.3
          ? "centered"
          : `${telemetry.lane_deviation.toFixed(1)} m off`,
      note:
        laneRatio >= 0.75 ? "drifting" : laneRatio >= 0.45 ? "off-centre" : "centred",
      fill: clampPercent(laneRatio * 100),
      tone: toneFor(laneRatio),
    },
    {
      key: "headway",
      icon: Car,
      label: "Following distance",
      value: `${telemetry.headway_distance.toFixed(0)} m`,
      note:
        headwayRisk >= 75 ? "too close" : headwayRisk >= 45 ? "moderate" : "safe gap",
      fill: headwayRisk,
      tone: toneFor(headwayRisk / 100),
    },
  ];
};

export function VehicleDynamics({ telemetry }: VehicleDynamicsProps) {
  if (!telemetry) {
    return (
      <div className="empty-state">
        No vehicle data for this moment — telemetry signal dropped.
      </div>
    );
  }

  const rows = buildRows(telemetry);

  return (
    <div className="vehicle-dynamics">
      {rows.map((row) => {
        const Icon = row.icon;
        return (
          <div className="vehicle-dynamics__row" key={row.key}>
            <div className="vehicle-dynamics__head">
              <span className="vehicle-dynamics__label">
                <Icon size={16} />
                {row.label}
              </span>
              <span className="vehicle-dynamics__value">
                {row.value}
                <small className={`vehicle-dynamics__note is-${row.tone}`}>
                  {row.note}
                </small>
              </span>
            </div>
            <div className="vehicle-dynamics__track">
              <div
                className={`vehicle-dynamics__fill is-${row.tone}`}
                style={{ width: `${row.fill}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
