import css from "./SlashPicker.module.css";
import type { SlashCommand } from "../types";

export function SlashPicker(props: {
  open: boolean;
  query: string;
  commands: SlashCommand[];
  onPick: (name: string) => void;
}) {
  const q = props.query.replace(/^\//, "").toLowerCase();
  const filtered = props.commands.filter((c) =>
    c.name.slice(1).toLowerCase().includes(q),
  );
  return (
    <div className={`picker ${css.picker} ${props.open ? "open " + css.open : ""}`}>
      <div className={css.head}>
        <span className={css.title}>commands & skills</span>
        <span className={css.count}>{filtered.length} matches</span>
      </div>
      {filtered.length === 0 ? (
        <div className={css.empty}>no matches for {props.query}</div>
      ) : (
        filtered.map((c) => (
          <button
            type="button"
            key={c.name}
            className={css.cmd}
            onClick={() => props.onPick(c.name)}
          >
            <div className={css.row}>
              <span className={css.name}>{c.name}</span>
              {c.kind === "skill" && <span className={css.tag}>skill</span>}
            </div>
            <div className={css.desc}>{c.description}</div>
          </button>
        ))
      )}
    </div>
  );
}
