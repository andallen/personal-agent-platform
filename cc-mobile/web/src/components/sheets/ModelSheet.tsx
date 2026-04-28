import { BottomSheet } from "../BottomSheet";
import "./sheets.css";
import type { Model } from "../../types";

export function ModelSheet(props: {
  open: boolean;
  current: string | null;
  models: Model[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <BottomSheet open={props.open} onClose={props.onClose}>
      <h3 className="sheetH3">model</h3>
      {props.models.map((m) => (
        <button
          key={m.id}
          className={`option ${props.current === m.id ? "optionActive" : ""}`}
          onClick={() => {
            props.onPick(m.id);
            props.onClose();
          }}
        >
          <span>
            <span className="oName">{m.label}</span>
            <br />
            <span className="oSub">{m.id}</span>
          </span>
          <span className="check">✓</span>
        </button>
      ))}
    </BottomSheet>
  );
}
