"use client";

import Link from "next/link";
import { useState } from "react";
import { Callout, PageHead } from "../../components/ui";

const fmt$ = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const fmt1 = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 1 });

function Num({ id, label, hint, value, set, min = 0, max, step = 1, suffix }: {
  id: string; label: string; hint?: string; value: number; set: (n: number) => void;
  min?: number; max?: number; step?: number; suffix?: string;
}) {
  const invalid = !Number.isFinite(value) || value < min || (max !== undefined && value > max);
  return (
    <div className="field">
      <label htmlFor={id}>{label}{suffix ? <span className="muted"> ({suffix})</span> : null}</label>
      <input id={id} type="number" inputMode="decimal" min={min} max={max} step={step} value={value}
        aria-invalid={invalid} aria-describedby={hint || invalid ? `${id}-h` : undefined}
        onChange={(e) => set(Number(e.target.value))} />
      {(hint || invalid) && <p className="hint" id={`${id}-h`} style={invalid ? { color: "var(--bad)" } : undefined}>
        {invalid ? `Enter a value${max !== undefined ? ` between ${min} and ${max}` : ` of at least ${min}`}.` : hint}</p>}
    </div>
  );
}

export default function Roi() {
  const [workflows, setWorkflows] = useState(50);
  const [failurePct, setFailurePct] = useState(10);
  const [costPer, setCostPer] = useState(150);
  const [hoursPer, setHoursPer] = useState(4);
  const [autoPct, setAutoPct] = useState(60);

  const clamp = (v: number, lo: number, hi = Infinity) => (Number.isFinite(v) ? Math.min(Math.max(v, lo), hi) : lo);
  const w = clamp(workflows, 0), f = clamp(failurePct, 0, 100), c = clamp(costPer, 0), h = clamp(hoursPer, 0), a = clamp(autoPct, 0, 100);

  const incidents = (w * f) / 100;
  const manualCost = incidents * c;
  const autoRecovered = (incidents * a) / 100;
  const savedMonth = autoRecovered * c;
  const hoursSaved = autoRecovered * h;

  return (
    <div>
      <PageHead eyebrow="Decision support" title="Value calculator"
        sub="A transparent model of what automatic recovery could be worth to your team. Every input is your assumption; nothing here is a customer result or a guarantee." />

      <div className="split even">
        <section className="card" aria-labelledby="assume-title">
          <h2 id="assume-title">1 · Your assumptions</h2>
          <p className="small muted">Editable. Replace the defaults with your own numbers.</p>
          <Num id="wf" label="Multi-system workflows per month" value={workflows} set={setWorkflows} min={0} />
          <Num id="fr" label="Share that fail midway" suffix="%" value={failurePct} set={setFailurePct} min={0} max={100} />
          <Num id="cost" label="Fully loaded cost to clean up one failure" suffix="USD" value={costPer} set={setCostPer} min={0}
            hint="Engineer time, escalations, customer impact. Use your own figure." />
          <Num id="hrs" label="Hours to clean up one failure" value={hoursPer} set={setHoursPer} min={0} step={0.5} />
          <Num id="auto" label="Share REVERSA would recover without a person" suffix="%" value={autoPct} set={setAutoPct} min={0} max={100}
            hint="Depends on how many of your steps are reversible. Irreversible and manual-only steps always need a person." />
        </section>

        <div>
          <section className="card" aria-labelledby="proj-title">
            <h2 id="proj-title">2 · Projected impact</h2>
            <p className="small muted">Calculated from your assumptions only. Not measured.</p>
            <div className="metrics" style={{ marginBottom: 12 }} aria-live="polite">
              <div className="metric"><div className="metric-label">Cleanup cost avoided / month</div>
                <div className="metric-value">{fmt$(savedMonth)}</div></div>
              <div className="metric"><div className="metric-label">Per year</div>
                <div className="metric-value">{fmt$(savedMonth * 12)}</div></div>
              <div className="metric"><div className="metric-label">Hours returned / month</div>
                <div className="metric-value">{fmt1(hoursSaved)} h</div></div>
            </div>
            <table>
              <caption className="sr-only">Calculation</caption>
              <tbody>
                <tr><td>Failed workflows / month</td><td className="num">{fmt1(incidents)}</td></tr>
                <tr><td>Current cleanup cost / month</td><td className="num">{fmt$(manualCost)}</td></tr>
                <tr><td>Recovered automatically / month</td><td className="num">{fmt1(autoRecovered)}</td></tr>
                <tr><td>Still handled by a person / month</td><td className="num">{fmt1(incidents - autoRecovered)}</td></tr>
              </tbody>
            </table>
            <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
              failed = workflows × failure share · avoided = failed × auto-recovery share × cost per failure.
            </p>
          </section>

          <section className="card" aria-labelledby="measured-title">
            <h2 id="measured-title">3 · What we have measured</h2>
            <p className="small">On the live demo deployment (one Vultr VM, demo connectors), 5 of 5 injected
              billing failures were fully compensated, with a median recovery time of 1.78 s.</p>
            <p className="small muted">That is a small benchmark on synthetic demo systems, not evidence of an
              enterprise recovery rate, so it is deliberately not used as the default above.{" "}
              <Link href="/demo-lab">Reproduce it in Demo Lab</Link>.</p>
          </section>
        </div>
      </div>

      <Callout tone="info" title="Not yet validated">
        <p className="small">REVERSA has no paying customers yet. Savings, pricing and adoption are unverified.
          A sandbox pilot with pre-registered success criteria is how these assumptions get tested.</p>
      </Callout>
    </div>
  );
}
