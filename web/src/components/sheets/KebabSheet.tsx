import { BottomSheet } from "../BottomSheet";
import "./sheets.css";

type Action = "resume" | "clear" | "compact";

export function KebabSheet(props: {
  open: boolean;
  onAction: (a: Action) => void;
  onClose: () => void;
}) {
  return (
    <BottomSheet open={props.open} onClose={props.onClose}>
      <h3 className="sheetH3">actions</h3>
      <button className="option" onClick={() => props.onAction("resume")}>
        <span className="oName">resume session…</span>
      </button>
      <button className="option" onClick={() => props.onAction("clear")}>
        <span className="oName">/clear</span>
      </button>
      <button className="option" onClick={() => props.onAction("compact")}>
        <span className="oName">/compact</span>
      </button>
    </BottomSheet>
  );
}
