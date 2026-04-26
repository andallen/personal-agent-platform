import "./messages.css";

const LABELS = {
  allow_once: "allowed once",
  allow_always: "allowed always",
  deny: "denied",
} as const;

export function PermissionPromptCard(props: {
  id: string;
  kind: string;
  target: string;
  resolved?: keyof typeof LABELS;
  onDecision: (d: keyof typeof LABELS) => void;
}) {
  return (
    <div className={`perm ${props.resolved ? "resolved" : ""}`}>
      <h4>{props.resolved ? `${props.kind} · resolved` : "permission required"}</h4>
      <div className="target">{props.target}</div>
      {props.resolved ? (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-dim)" }}>
          {LABELS[props.resolved]}
        </div>
      ) : (
        <div className="perm-actions">
          <button className="btn-primary" onClick={() => props.onDecision("allow_once")}>
            Allow once
          </button>
          <button className="btn-secondary" onClick={() => props.onDecision("allow_always")}>
            Always
          </button>
          <button className="btn-text" onClick={() => props.onDecision("deny")}>
            Deny
          </button>
        </div>
      )}
    </div>
  );
}
