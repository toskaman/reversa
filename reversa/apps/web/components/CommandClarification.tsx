interface Props {
  questions: string[];
  provider: string;
  onDismiss: () => void;
}

// Cycle 2 §2: ambiguous intent → questions, NO workflow created.
// Display-only by design (multi-turn dialogue state is a spec non-goal):
// the user refines the intent in the form and re-plans.
export default function CommandClarification({ questions, provider, onDismiss }: Props) {
  return (
    <div className="callout warn" role="status">
      <span className="callout-glyph" aria-hidden="true">?</span>
      <div className="callout-body">
        <p><strong>Needs clarification</strong></p>
        <p className="muted">
          The request is ambiguous, so no plan was generated and no workflow was
          created{provider ? ` (planner: ${provider})` : ""}. Refine it above and generate again:
        </p>
        {questions.length > 0 ? (
          <ol style={{ margin: "0 0 12px", paddingLeft: 20 }}>
            {questions.map((q, i) => <li key={i}>{q}</li>)}
          </ol>
        ) : (
          <p className="muted">
            The planner needs more detail, for example which company, how many
            accounts, or which systems are in scope.
          </p>
        )}
        <div className="actions"><button className="ghost" onClick={onDismiss}>Dismiss</button></div>
      </div>
    </div>
  );
}
