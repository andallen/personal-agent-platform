import { useState } from "react";
import "./messages.css";

const KIND_CLASS: Record<string, string> = {
  Bash: "",
  Edit: "edit",
  Read: "read",
  Write: "edit",
};

export function ToolCallCard(props: {
  name: string;
  input: Record<string, unknown>;
  result?: string;
}) {
  const [open, setOpen] = useState(false);
  const summary =
    typeof props.input["command"] === "string"
      ? (props.input["command"] as string)
      : typeof props.input["file_path"] === "string"
        ? (props.input["file_path"] as string)
        : JSON.stringify(props.input).slice(0, 80);
  const klass = KIND_CLASS[props.name] ?? "";
  return (
    <div className="tool">
      <button
        type="button"
        className="tool-summary"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={`glyph ${klass}`}>{props.name.toLowerCase()}</span>
        <span className="cmd">{summary}</span>
        <span className="chev">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="tool-body">{props.result ?? "(no output)"}</div>}
    </div>
  );
}
