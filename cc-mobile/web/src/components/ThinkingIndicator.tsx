import css from "./ThinkingIndicator.module.css";

export function ThinkingIndicator(props: { open: boolean }) {
  return (
    <div
      className={`${css.bar} ${props.open ? css.open : ""}`}
      role="status"
      aria-live="polite"
      aria-hidden={!props.open}
    >
      <span className={css.thinking}>Thinking...</span>
    </div>
  );
}
