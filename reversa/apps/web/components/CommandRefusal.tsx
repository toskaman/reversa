interface Props {
  code: string;
  reason: string;
  provider: string;
  onDismiss: () => void;
}

// Cycle 2 §3: off-scope intent → explicit refusal code, NO workflow.
export default function CommandRefusal({ code, reason, provider, onDismiss }: Props) {
  return (
    <div className="card" role="alert">
      <h2>
        <span className="badge b-red">REFUSED</span>{" "}
        <code>{code}</code>
      </h2>
      <p>{reason}</p>
      <p className="muted">
        No workflow was created{provider ? ` (provider: ${provider})` : ""}.
        REVERSA plans onboarding, offboarding and escalation requests —
        please rephrase your intent within one of these domains.
      </p>
      <button className="ghost" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}
