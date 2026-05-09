export const formatPercent = (value: number) => `${Math.round(value * 100)}%`;

export const formatProbability = (value: number) => value.toFixed(2);

export const formatRiskScore = (value: number) =>
  `${value.toFixed(1)} / 100`;

export const formatContribution = (value: number) =>
  `${Math.round(value)} / 100`;

export const formatTimestamp = (timestamp: string) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(timestamp));
