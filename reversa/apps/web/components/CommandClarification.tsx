interface Props {
  questions: string[];
  provider: string;
  onDismiss: () => void;
}

// Cycle 2 §2: ambiguous intent → questions, NO workflow created.
// Display-only by design (multi-turn dialogue state is a spec non-goal):
// the user refines the intent in the Command Center form and re-plans.
export default function CommandClarification({ questions, provider, onDismiss }: Props) {
  return (
    <div className="card" role="status" aria-live="polite">
      <h2>
        <span className="badge b-amber">NEEDS CLARIFICATION</span>
      </h2>
      <p className="muted">
        Your intent is ambiguous, so no plan was generated and no workflow was
        created. Please refine your intent below{provider ? ` (provider: ${provider})` : ""}:
      </p>
      {questions.length > 0 ? (
        <ol>
          {questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ol>
      ) : (
        <p className="muted">
          The planner needs more detail — for example which company, how many
          accounts, or which systems are in scope.
        </p>
      )}
      <button className="ghost" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}
