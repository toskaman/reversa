"use client";

import WorkflowList from "../../components/WorkflowList";
import { PageHead } from "../../components/ui";
import { TERMINAL } from "../../lib/status";

export default function EvidenceIndex() {
  return (
    <div>
      <PageHead title="Evidence" sub="Each workflow produces an Evidence Passport: a hash-chained record of what was planned, approved, executed and reversed. Open one to check its chain and export it for independent verification." />
      <WorkflowList caption="Evidence passports" link="evidence" filters={[
        { id: "final", label: "Finished runs", match: (w) => TERMINAL.has(w.state) },
        { id: "all", label: "All", match: () => true },
      ]} />
    </div>
  );
}
