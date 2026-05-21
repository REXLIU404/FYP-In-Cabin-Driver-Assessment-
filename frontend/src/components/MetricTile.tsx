interface MetricTileProps {
  label: string;
  value: string;
  detail?: string;
}

export function MetricTile({ label, value, detail }: MetricTileProps) {
  return (
    <div className="metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}
