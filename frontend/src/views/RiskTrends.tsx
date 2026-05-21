import { BarChart3 } from "lucide-react";
import { DistributionChart } from "../components/DistributionChart";
import { Pill } from "../components/Pill";
import { TrendChart } from "../components/TrendChart";
import type { DistributionDatum, RiskLevel, RiskUpdate } from "../types";
import { getEvidenceType } from "../../../ai/src/evidence";
import { formatRiskScore, formatTimestamp } from "../utils/format";

interface RiskTrendsProps {
  history: RiskUpdate[];
  selectedWindowId: number;
  thresholdLow: number;
  onSelectWindow: (windowId: number) => void;
}

const riskLevels: RiskLevel[] = ["Low", "Medium", "High"];

const distribution = (history: RiskUpdate[]): DistributionDatum[] =>
  riskLevels.map((label) => ({
    label,
    count: history.filter((record) => record.RiskLevel === label).length,
  }));

export function RiskTrends({
  history,
  selectedWindowId,
  thresholdLow,
  onSelectWindow,
}: RiskTrendsProps) {
  return (
    <div className="page-grid page-grid--trends">
      <section className="panel panel--wide">
        <div className="section-header">
          <div>
            <p className="eyebrow">Risk Trends</p>
            <h2>RiskScore and modality traces</h2>
          </div>
          <BarChart3 size={20} />
        </div>
        <TrendChart history={history} />
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Distribution</p>
            <h2>RiskLevel counts</h2>
          </div>
        </div>
        <DistributionChart data={distribution(history)} />
      </section>

      <section className="panel panel--full">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Window</th>
                <th>Time</th>
                <th>RiskScore</th>
                <th>RiskLevel</th>
                <th>Alert</th>
                <th>Evidence Type</th>
                <th>Flag</th>
              </tr>
            </thead>
            <tbody>
              {[...history].reverse().map((record) => (
                <tr
                  key={record.window_id}
                  className={[
                    record.window_id === selectedWindowId ? "is-selected" : "",
                    record.RiskLevel === "High" ? "is-high-risk" : "",
                  ].join(" ")}
                  onClick={() => onSelectWindow(record.window_id)}
                >
                  <td>{record.window_id}</td>
                  <td>{formatTimestamp(record.timestamp)}</td>
                  <td>{formatRiskScore(record.RiskScore)}</td>
                  <td>
                    <Pill label={record.RiskLevel} tone={record.RiskLevel} />
                  </td>
                  <td>
                    <Pill
                      label={record.AlertSeverity}
                      tone={record.AlertSeverity}
                    />
                  </td>
                  <td>{getEvidenceType(record, thresholdLow)}</td>
                  <td>
                    {record.flagged ? (
                      <Pill label="flagged" tone="flagged" />
                    ) : (
                      "None"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
