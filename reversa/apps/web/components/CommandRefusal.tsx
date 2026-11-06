interface Props {
  code: string;
  reason: string;
  provider: string;
  onDismiss: () => void;
}

// Cycle 2 §3: off-scope intent → explicit refusal code, NO workflow.
export default function CommandRefusal({ code, reason, provider, onDismiss }: Props) {
  return (
    <div className="callout bad" role="alert">
      <span className="callout-glyph" aria-hidden="true">✕</span>
      <div className="callout-body">
        <p><strong>Request refused</strong> <code>{code}</code></p>
        <p>{reason}</p>
        <p className="muted small">
          No workflow was created{provider ? ` (planner: ${provider})` : ""}.
          REVERSA plans onboarding, offboarding and escalation requests.
          Rephrase your request within one of these.
        </p>
        <div className="actions"><button className="ghost" onClick={onDismiss}>Dismiss</button></div>
      </div>
    </div>
  );
}
