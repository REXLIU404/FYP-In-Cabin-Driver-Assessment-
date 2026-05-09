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
      <ResponsiveContainer width="100%" height={240}>
        <BarChart
          data={data}
          margin={{ top: 12, right: 10, bottom: 4, left: -18 }}
        >
          <CartesianGrid stroke="#e5e7eb" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
          <Tooltip />
          <Bar dataKey="count" fill="#2563eb" radius={[8, 8, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
