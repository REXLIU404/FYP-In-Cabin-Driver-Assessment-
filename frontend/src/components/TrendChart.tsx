import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RiskUpdate } from "../types";
import { formatRiskScore } from "../utils/format";

interface TrendChartProps {
  history: RiskUpdate[];
}

export function TrendChart({ history }: TrendChartProps) {
  const data = history.map((record) => ({
    window: record.window_id,
    risk: record.RiskScore,
    vision: record.P_distraction * 100,
    telemetry: record.P_telemetry_anomaly * 100,
  }));

  return (
    <div className="trend-chart" aria-label="Risk score timeline">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart
          data={data}
          margin={{ top: 16, right: 20, bottom: 8, left: 0 }}
        >
          <CartesianGrid stroke="#e5e7eb" vertical={false} />
          <XAxis dataKey="window" tickLine={false} axisLine={false} />
          <YAxis
            domain={[0, 100]}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => Number(value).toFixed(0)}
          />
          <ReferenceLine
            y={30}
            stroke="#f59e0b"
            strokeDasharray="5 5"
            label="30"
          />
          <ReferenceLine
            y={60}
            stroke="#ef4444"
            strokeDasharray="5 5"
            label="60"
          />
          <Tooltip
            formatter={(value, name) =>
              name === "RiskScore"
                ? formatRiskScore(Number(value))
                : `${Number(value).toFixed(1)}%`
            }
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="risk"
            name="RiskScore"
            stroke="#111827"
            strokeWidth={3}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="vision"
            name="P_distraction (%)"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="telemetry"
            name="P_telemetry_anomaly (%)"
            stroke="#059669"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
