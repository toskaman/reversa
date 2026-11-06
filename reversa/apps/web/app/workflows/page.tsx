"use client";

import Link from "next/link";
import WorkflowList from "../../components/WorkflowList";
import { PageHead } from "../../components/ui";
import { ACTIVE, ATTENTION, RECOVERY } from "../../lib/status";

export default function WorkflowsPage() {
  return (
    <div>
      <PageHead title="Workflows" sub="Every multi-system operation in this organization, newest first."
        actions={<Link className="btn" href="/command">New workflow</Link>} />
      <WorkflowList caption="Workflows" link="workflow" filters={[
        { id: "all", label: "All", match: () => true },
        { id: "active", label: "In progress", match: (w) => ACTIVE.has(w.state) },
        { id: "attention", label: "Needs attention", match: (w) => ATTENTION.has(w.state) },
        { id: "done", label: "Completed", match: (w) => w.state === "COMPLETED" },
        { id: "recovery", label: "Recovered or failed", match: (w) => RECOVERY.has(w.state) },
      ]} />
    </div>
  );
}
