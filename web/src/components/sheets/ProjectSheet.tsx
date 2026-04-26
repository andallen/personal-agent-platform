import { BottomSheet } from "../BottomSheet";
import "./sheets.css";
import type { Project } from "../../types";

export function ProjectSheet(props: {
  open: boolean;
  current: string;
  projects: Project[];
  onPick: (cwd: string) => void;
  onClose: () => void;
}) {
  return (
    <BottomSheet open={props.open} onClose={props.onClose}>
      <h3 className="sheetH3">project</h3>
      {props.projects.map((p) => (
        <button
          key={p.cwd}
          className={`option ${props.current === p.cwd ? "optionActive" : ""}`}
          onClick={() => {
            props.onPick(p.cwd);
            props.onClose();
          }}
        >
          <span>
            <span className="oName">{p.name}</span>
            <br />
            <span className="oSub">{p.cwd}</span>
          </span>
          <span className="check">✓</span>
        </button>
      ))}
    </BottomSheet>
  );
}
