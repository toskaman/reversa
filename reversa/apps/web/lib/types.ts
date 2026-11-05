export interface Workflow {
  id: number; org_slug: string; name: string; intent: string; state: string;
  plan_version: number; plan_hash: string; steps: number; created_by: string;
}
export interface Action {
  seq: number; action_type: string; connector_id: string; state: string;
  attempt: number; max_attempts: number; compensation_capability: string;
  depends_on: number[]; error: string;
}
export interface Evt {
  seq: number; ts: string; type: string; actor: string;
  payload: Record<string, unknown>; prev_hash?: string; hash?: string;
}
export interface Preview {
  plan_hash: string; steps: number;
  effects: { connector_id: string; effects: string[];
    compensation_capability: string; approval_policy: string; risk_level: string }[];
  approvals_required: boolean; irreversible: string[]; limits: string[];
}
export interface Bundle {
  generator: string; exported_at: string; org_slug: string;
  workflow: Workflow & { created_at: string; updated_at: string };
  plan: { goal: string; steps: unknown[] };
  actions: (Action & { inputs: unknown; output: unknown })[];
  events: (Evt & { org_id: number; prev_hash: string; hash: string })[];
  approvals: { plan_version: number; status: string; requested_by: string;
    decided_by: string }[];
  chain: { valid: boolean; bad_seq: number; message: string };
  limits: string[];
}
