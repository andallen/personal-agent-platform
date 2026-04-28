import css from "./TopBar.module.css";

type SheetId = "project" | "mode" | "model" | "effort" | "kebab";

export function TopBar(props: {
  project: string;
  mode: string;
  model: string;
  effort: string;
  onOpen: (id: SheetId) => void;
}) {
  const modeWarn = props.mode === "bypass" ? "warn" : "";
  return (
    <header className={`${css.bar}`}>
      <div className={css.row}>
        <button
          className={`${css.pill}`}
          aria-label="project"
          onClick={() => props.onOpen("project")}
        >
          <span className={css.label}>/</span>
          <span className={css.value}>{props.project}</span>
          <span className={css.caret}>▾</span>
        </button>
        <button
          className={`${css.pill} ${modeWarn ? css.warn : ""}`}
          aria-label="mode"
          onClick={() => props.onOpen("mode")}
        >
          <span className={css.label}>mode</span>
          <span className={css.value}>{props.mode}</span>
          <span className={css.caret}>▾</span>
        </button>
        <button
          className={`${css.pill} ${css.active}`}
          aria-label="model"
          onClick={() => props.onOpen("model")}
        >
          <span className={css.label}>model</span>
          <span className={css.value}>{props.model}</span>
          <span className={css.caret}>▾</span>
        </button>
        <button
          className={`${css.pill}`}
          aria-label="effort"
          onClick={() => props.onOpen("effort")}
        >
          <span className={css.label}>effort</span>
          <span className={css.value}>{props.effort}</span>
          <span className={css.caret}>▾</span>
        </button>
        <button
          className={`${css.pill} ${css.kebab}`}
          aria-label="more"
          onClick={() => props.onOpen("kebab")}
        >
          ⋯
        </button>
      </div>
    </header>
  );
}
