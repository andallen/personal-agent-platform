import { BottomSheet } from "../BottomSheet";
import "./sheets.css";

const SUB: Record<string, string> = {
  default: "prompts on each tool",
  accept_edits: "edits auto-allowed",
  plan: "read-only, plan first",
  bypass: "--dangerously-skip-permissions",
};

export function ModeSheet(props: {
  open: boolean;
  current: string;
  modes: string[];
  onPick: (m: string) => void;
  onClose: () => void;
}) {
  return (
    <BottomSheet open={props.open} onClose={props.onClose}>
      <h3 className="sheetH3">mode</h3>
      {props.modes.map((m) => (
        <button
          key={m}
          className={`option ${props.current === m ? "optionActive" : ""}`}
          onClick={() => {
            props.onPick(m);
            props.onClose();
          }}
        >
          <span>
            <span className="oName">{m}</span>
            <br />
            <span className="oSub">{SUB[m] ?? ""}</span>
          </span>
          <span className="check">✓</span>
        </button>
      ))}
    </BottomSheet>
  );
}
