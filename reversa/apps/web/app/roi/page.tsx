"use client";

import { useState } from "react";

export default function Roi() {
  const [workflows, setWorkflows] = useState(50);
  const [failurePct, setFailurePct] = useState(10);
  const [costPer, setCostPer] = useState(150);
  const [hoursPer, setHoursPer] = useState(4);
  const [autoPct, setAutoPct] = useState(100);

  const incidents = (workflows * failurePct) / 100;
  const manualCost = incidents * costPer;
  const manualHours = incidents * hoursPer;
  const autoRecovered = (incidents * autoPct) / 100;
  const savedMonth = autoRecovered * costPer;
  const savedYear = savedMonth * 12;
  const hoursSaved = autoRecovered * hoursPer;

  const num = (v: number, set: (n: number) => void, min = 0) => (
    <input type="number" min={min} value={v}
      onChange={(e) => set(Number(e.target.value))} />
  );

  return (
    <div>
      <h1>Value calculator</h1>
      <p className="sub">Hypotheses you can edit. No invented customers or savings.</p>
      <div className="row">
        <div className="card">
          <h2>Your hypotheses</h2>
          <label>Workflows per month</label>{num(workflows, setWorkflows, 1)}
          <label>Failure rate (%)</label>{num(failurePct, setFailurePct)}
          <label>Manual recovery cost per incident ($)</label>{num(costPer, setCostPer)}
          <label>Recovery time per incident (hours)</label>{num(hoursPer, setHoursPer)}
          <label>Auto-compensated share (%) — default 100% is our measured
            demo-benchmark rate (5 chaos runs, see docs/benchmarks)</label>
          {num(autoPct, setAutoPct)}
        </div>
        <div className="card">
          <h2>Projection</h2>
          <table><tbody>
            <tr><td>Incidents / month</td><td><b>{incidents.toFixed(1)}</b></td></tr>
            <tr><td>Manual cost / month</td><td><b>${manualCost.toFixed(0)}</b></td></tr>
            <tr><td>Manual hours / month</td><td><b>{manualHours.toFixed(1)} h</b></td></tr>
            <tr><td>Auto-recovered / month</td><td><b>{autoRecovered.toFixed(1)}</b></td></tr>
            <tr><td>Hours saved / month</td><td><b>{hoursSaved.toFixed(1)} h</b></td></tr>
            <tr><td>Saved / month</td><td><b>${savedMonth.toFixed(0)}</b></td></tr>
            <tr><td>Saved / year</td><td><b>${savedYear.toFixed(0)}</b></td></tr>
          </tbody></table>
          <p className="muted">Formulas: incidents = workflows × rate;
            saved = incidents × auto-share × cost. Sources: your inputs +
            our measured recovery rate (demo benchmark, n=5).</p>
        </div>
      </div>
    </div>
  );
}
