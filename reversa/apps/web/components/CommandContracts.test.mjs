// Durable unit tests for the Cycle 2 intent-response contracts.
// Runner: node --test (no dependencies; the subject module uses erasable
// TS only, stripped natively by Node >= 22.18). Run from reversa/apps/web:
//   node --test components/CommandContracts.test.mjs
// Plain .mjs (not .ts) so the repo's `tsc --noEmit` lint, which lacks
// allowImportingTsExtensions, stays green without touching tsconfig.
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  classifyIntentResponse,
  refusalFromApiError,
} from "./CommandContracts.ts";

const WF = {
  id: 7, org_slug: "acme", name: "Onboard Acme", intent: "onboard acme",
  state: "AWAITING_APPROVAL", plan_version: 1, plan_hash: "ab".repeat(32),
  steps: 11, created_by: "tester",
};

describe("classifyIntentResponse", () => {
  it("classifies the legacy 201 plan shape (no status field)", () => {
    const r = classifyIntentResponse({
      workflow: WF, plan_hash: "ab".repeat(32), approval_required: true,
      provider: "vultr", warnings: ["w1"],
    });
    assert.equal(r.kind, "plan");
    if (r.kind === "plan") {
      assert.equal(r.response.workflow.id, 7);
      assert.equal(r.response.provider, "vultr");
      assert.deepEqual(r.response.warnings, ["w1"]);
      assert.equal(r.response.approval_required, true);
    }
  });

  it("defaults optional plan fields defensively", () => {
    const r = classifyIntentResponse({ workflow: WF, plan_hash: "x" });
    assert.equal(r.kind, "plan");
    if (r.kind === "plan") {
      assert.equal(r.response.provider, "deterministic");
      assert.deepEqual(r.response.warnings, []);
      assert.equal(r.response.approval_required, false);
    }
  });

  it("classifies needs_clarification with questions", () => {
    const r = classifyIntentResponse({
      status: "needs_clarification",
      questions: ["Which company?", "How many seats?"],
      provider: "deterministic",
    });
    assert.equal(r.kind, "clarify");
    if (r.kind === "clarify") {
      assert.deepEqual(r.questions, ["Which company?", "How many seats?"]);
      assert.equal(r.provider, "deterministic");
    }
  });

  it("caps questions at 3 and drops non-strings", () => {
    const r = classifyIntentResponse({
      status: "needs_clarification",
      questions: ["q1", "", 42, "q2", "q3", "q4"],
    });
    assert.equal(r.kind, "clarify");
    if (r.kind === "clarify") {
      assert.deepEqual(r.questions, ["q1", "q2", "q3"]);
      assert.equal(r.provider, "deterministic");
    }
  });

  it("tolerates a missing questions array", () => {
    const r = classifyIntentResponse({ status: "needs_clarification" });
    assert.equal(r.kind, "clarify");
    if (r.kind === "clarify") assert.deepEqual(r.questions, []);
  });

  it("classifies refused with code and reason", () => {
    const r = classifyIntentResponse({
      status: "refused", code: "OUT_OF_SCOPE",
      reason: "not onboarding", provider: "vultr",
    });
    assert.equal(r.kind, "refuse");
    if (r.kind === "refuse") {
      assert.equal(r.code, "OUT_OF_SCOPE");
      assert.equal(r.reason, "not onboarding");
      assert.equal(r.provider, "vultr");
    }
  });

  it("falls back on refused with missing fields", () => {
    const r = classifyIntentResponse({ status: "refused" });
    assert.equal(r.kind, "refuse");
    if (r.kind === "refuse") {
      assert.equal(r.code, "OUT_OF_SCOPE");
      assert.ok(r.reason.length > 0);
    }
  });

  it("reports unknown shapes instead of guessing", () => {
    for (const body of [null, undefined, 42, "x", [], {},
        { status: "planned" }, { status: "ok", workflow: WF },
        { workflow: WF }, { plan_hash: "x" }]) {
      assert.equal(classifyIntentResponse(body).kind, "unknown",
        `body: ${JSON.stringify(body)}`);
    }
  });
});

describe("refusalFromApiError", () => {
  it("maps a 422 PLAN_REJECTED/OUT_OF_SCOPE error onto the refusal card", () => {
    const msg = '422: {"code": "PLAN_REJECTED", "issues": [{"code": "OUT_OF_SCOPE", ' +
      '"field": "intent", "message": "intent is outside onboarding scope"}]}';
    assert.deepEqual(refusalFromApiError(422, msg), {
      code: "OUT_OF_SCOPE",
      reason: "intent is outside onboarding scope",
    });
  });

  it("returns null for non-refusal errors", () => {
    assert.equal(refusalFromApiError(429, "429: rate limited"), null);
    assert.equal(refusalFromApiError(500, "500: boom"), null);
    assert.equal(
      refusalFromApiError(422, '422: {"code": "PLAN_REJECTED", "x": 1}'), null);
    assert.equal(refusalFromApiError(422, "422: other validation error"), null);
  });
});
