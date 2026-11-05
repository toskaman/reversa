// Durable unit tests for the Cycle 2 workflow-header provenance helpers.
// Runner: node --test (no dependencies; the subject module uses erasable
// TS only, stripped natively by Node >= 22.18). Run from reversa/apps/web:
//   node --test components/WorkflowHeaderProvenance.test.mjs
// Plain .mjs (not .ts) so the repo's `tsc --noEmit` lint, which lacks
// allowImportingTsExtensions, stays green without touching tsconfig.
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  extractProvenance,
  formatLatencyMs,
  provenanceBadgeClass,
  provenanceBadgeLabel,
  provenanceTooltip,
} from "./WorkflowHeaderProvenance.ts";

const DETERMINISTIC = {
  provider: "deterministic",
  model: "",
  latency_ms: 3,
  usage: {},
  warnings: [],
};

const VULTR = {
  provider: "vultr-inference",
  model: "qwen3-235b-a22b-instruct-2507",
  latency_ms: 12345,
  usage: { total_tokens: 9000, attempts: 1 },
  warnings: ["accepted after 2 attempt(s)"],
};

describe("extractProvenance", () => {
  it("extracts the deterministic planner payload", () => {
    assert.deepEqual(extractProvenance(DETERMINISTIC), {
      provider: "deterministic",
      model: "",
      latencyMs: 3,
      warnings: [],
    });
  });

  it("extracts the vultr planner payload with model and warnings", () => {
    assert.deepEqual(extractProvenance(VULTR), {
      provider: "vultr-inference",
      model: "qwen3-235b-a22b-instruct-2507",
      latencyMs: 12345,
      warnings: ["accepted after 2 attempt(s)"],
    });
  });

  it("normalizes unknown payloads to empty provenance", () => {
    const empty = { provider: "", model: "", latencyMs: null, warnings: [] };
    for (const payload of [null, undefined, 42, "x", [], {}]) {
      assert.deepEqual(extractProvenance(payload), empty,
        `payload: ${JSON.stringify(payload)}`);
    }
  });

  it("drops malformed field types instead of crashing", () => {
    assert.deepEqual(
      extractProvenance({
        provider: 42,
        model: ["qwen"],
        latency_ms: "fast",
        warnings: ["w1", "", 7, null],
      }),
      { provider: "", model: "", latencyMs: null, warnings: ["w1"] },
    );
  });

  it("rejects negative and non-finite latencies", () => {
    for (const latency_ms of [-1, NaN, Infinity]) {
      assert.equal(extractProvenance({ latency_ms }).latencyMs, null);
    }
    assert.equal(extractProvenance({ latency_ms: 0 }).latencyMs, 0);
  });
});

describe("formatLatencyMs", () => {
  it("formats recorded latencies", () => {
    assert.equal(formatLatencyMs(0), "0 ms");
    assert.equal(formatLatencyMs(12345), "12345 ms");
  });

  it("marks missing or invalid latencies as not recorded", () => {
    for (const v of [null, undefined, -1, NaN, Infinity]) {
      assert.equal(formatLatencyMs(v), "not recorded");
    }
  });
});

describe("provenanceBadgeClass", () => {
  const base = { provider: "", model: "", latencyMs: null, warnings: [] };

  it("is neutral when the provider was not recorded", () => {
    assert.equal(provenanceBadgeClass(base), "");
  });

  it("colors deterministic blue and vultr-inference violet", () => {
    assert.equal(
      provenanceBadgeClass({ ...base, provider: "deterministic" }), "b-blue");
    assert.equal(
      provenanceBadgeClass({ ...base, provider: "vultr-inference" }),
      "b-violet");
  });

  it("colors unknown providers blue", () => {
    assert.equal(
      provenanceBadgeClass({ ...base, provider: "other-llm" }), "b-blue");
  });

  it("colors amber when warnings exist, regardless of provider", () => {
    for (const provider of ["deterministic", "vultr-inference", "other"]) {
      assert.equal(
        provenanceBadgeClass({ ...base, provider, warnings: ["w"] }),
        "b-amber");
    }
  });
});

describe("provenanceBadgeLabel", () => {
  const base = { provider: "", model: "", latencyMs: null, warnings: [] };

  it("names the provider", () => {
    assert.equal(
      provenanceBadgeLabel({ ...base, provider: "vultr-inference" }),
      "planner: vultr-inference");
    assert.equal(
      provenanceBadgeLabel({ ...base, provider: "deterministic" }),
      "planner: deterministic");
  });

  it("marks an unrecorded provider", () => {
    assert.equal(provenanceBadgeLabel(base), "planner: not recorded");
  });

  it("appends the warning count", () => {
    assert.equal(
      provenanceBadgeLabel({
        ...base, provider: "deterministic", warnings: ["a", "b"],
      }),
      "planner: deterministic ⚠ 2");
  });
});

describe("provenanceTooltip", () => {
  it("quotes provider/model/latency and lists warnings", () => {
    const tip = provenanceTooltip(extractProvenance(VULTR));
    assert.ok(tip.includes("provider: vultr-inference"));
    assert.ok(tip.includes("model: qwen3-235b-a22b-instruct-2507"));
    assert.ok(tip.includes("latency: 12345 ms"));
    assert.ok(tip.includes("warnings (1):"));
    assert.ok(tip.includes("- accepted after 2 attempt(s)"));
  });

  it("marks missing values as not recorded with no warnings", () => {
    const tip = provenanceTooltip(extractProvenance({}));
    assert.ok(tip.includes("provider: not recorded"));
    assert.ok(tip.includes("model: not recorded"));
    assert.ok(tip.includes("latency: not recorded"));
    assert.ok(tip.includes("warnings: none"));
  });

  it("shows an empty deterministic model as not recorded", () => {
    const tip = provenanceTooltip(extractProvenance(DETERMINISTIC));
    assert.ok(tip.includes("provider: deterministic"));
    assert.ok(tip.includes("model: not recorded"));
    assert.ok(tip.includes("latency: 3 ms"));
    assert.ok(tip.includes("warnings: none"));
  });
});
