import { BottomSheet } from "../BottomSheet";
import "./sheets.css";
import type { Session } from "../../types";

export function ResumeSheet(props: {
  open: boolean;
  sessions: Session[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <BottomSheet open={props.open} onClose={props.onClose} noScroll>
      <h3 className="sheetH3">resume session</h3>
      {props.sessions.map((s) => (
        <button
          key={s.id}
          className="option"
          onClick={() => {
            props.onPick(s.id);
            props.onClose();
          }}
        >
          <span>
            <span className="oName">{s.title ?? s.id.slice(0, 12)}</span>
            <br />
            <span className="oSub">
              {new Date(s.mtime * 1000).toLocaleString()}
            </span>
          </span>
        </button>
      ))}
    </BottomSheet>
  );
}
