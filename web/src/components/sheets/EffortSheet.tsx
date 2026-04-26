import { BottomSheet } from "../BottomSheet";
import "./sheets.css";

export function EffortSheet(props: {
  open: boolean;
  current: string | null;
  efforts: string[];
  onPick: (e: string) => void;
  onClose: () => void;
}) {
  return (
    <BottomSheet open={props.open} onClose={props.onClose}>
      <h3 className="sheetH3">effort</h3>
      {props.efforts.map((e) => (
        <button
          key={e}
          className={`option ${props.current === e ? "optionActive" : ""}`}
          onClick={() => {
            props.onPick(e);
            props.onClose();
          }}
        >
          <span className="oName">{e}</span>
          <span className="check">✓</span>
        </button>
      ))}
    </BottomSheet>
  );
}
