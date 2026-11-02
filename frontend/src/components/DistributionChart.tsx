import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DistributionDatum } from "../types";

interface DistributionChartProps {
  data: DistributionDatum[];
}

export function DistributionChart({ data }: DistributionChartProps) {
  return (
    <div className="distribution-chart">
      {/* Horizontal bars: the category names sit on the Y axis, one per line, so all of them
          stay readable in a narrow panel. Upright bars dropped or overlapped half the names. */}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 18, left: 0 }}
        >
          <CartesianGrid stroke="#e5e7eb" horizontal={false} />
          <XAxis
            type="number"
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            label={{
              value: "Windows",
              position: "insideBottom",
              offset: -12,
              style: { fontSize: 11, fill: "#64748b" },
            }}
          />
          <YAxis
            type="category"
            dataKey="label"
            tickLine={false}
            axisLine={false}
            interval={0}
            width={84}
            tick={{ fontSize: 11 }}
          />
          <Tooltip />
          <Bar dataKey="count" fill="#2563eb" radius={[0, 6, 6, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
