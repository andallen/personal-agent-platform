import css from "./CompactingIndicator.module.css";

export function CompactingIndicator(props: { open: boolean }) {
  return (
    <div
      className={`${css.bar} ${props.open ? css.open : ""}`}
      role="status"
      aria-live="polite"
      aria-hidden={!props.open}
    >
      <span className={css.compacting}>Compacting...</span>
    </div>
  );
}
