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
import { formatFixed } from "../utils/format";
import { buildTrendSeries, formatTrendTooltip } from "./trendSeries";

interface TrendChartProps {
  history: RiskUpdate[];
  thresholdLow?: number;
  thresholdHigh?: number;
}

export function TrendChart({
  history,
  thresholdLow = 30,
  thresholdHigh = 60,
}: TrendChartProps) {
  const data = buildTrendSeries(history);

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
            tickFormatter={(value) => formatFixed(Number(value), 0)}
          />
          <ReferenceLine
            y={thresholdLow}
            stroke="#f59e0b"
            strokeDasharray="5 5"
            label={String(thresholdLow)}
          />
          <ReferenceLine
            y={thresholdHigh}
            stroke="#ef4444"
            strokeDasharray="5 5"
            label={String(thresholdHigh)}
          />
          {/* filterNull={false}: a null point (an unassessed window, a missing
              branch) must reach the formatter and read "Unavailable" instead of
              being silently left out of the tooltip. */}
          <Tooltip
            filterNull={false}
            formatter={(value, name) => formatTrendTooltip(value, name)}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="risk"
            name="RiskScore"
            stroke="#111827"
            strokeWidth={3}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="vision"
            name="P_distraction (%)"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="telemetry"
            name="Telemetry non-safe (%)"
            stroke="#059669"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
