import type { ReactElement } from "react";
import type { ServerEvent, PermissionPrompt } from "../../types";
import { AssistantMessage } from "./AssistantMessage";
import { UserMessage } from "./UserMessage";
import { ToolCallCard } from "./ToolCallCard";
import { ClearDivider, CompactDivider } from "./ClearDivider";
import { PermissionPromptCard } from "./PermissionPromptCard";
import "./messages.css";

type Decision = "allow_once" | "allow_always" | "deny";

export function MessageList(props: {
  events: ServerEvent[];
  permissions: Record<string, PermissionPrompt & { resolved?: Decision }>;
  onDecision: (id: string, d: Decision) => void;
}) {
  // /clear hides everything before the most recent clear_marker. The marker
  // itself is kept so its divider still renders as a visual confirmation.
  let lastClearIdx = -1;
  props.events.forEach((e, idx) => {
    if (e.kind === "chat_event" && e.event.kind === "clear_marker") lastClearIdx = idx;
  });
  const visible = lastClearIdx > 0 ? props.events.slice(lastClearIdx) : props.events;

  const toolResults: Record<string, string> = {};
  for (const e of visible) {
    if (e.kind === "chat_event" && e.event.kind === "tool_result") {
      toolResults[e.event.tool_use_id] = e.event.content;
    }
  }

  const items: ReactElement[] = [];
  let i = 0;
  for (const e of visible) {
    if (e.kind !== "chat_event") continue;
    const ev = e.event;
    const k = i++;
    if (ev.kind === "user_message") items.push(<UserMessage key={k} text={ev.text} />);
    else if (ev.kind === "assistant_text") items.push(<AssistantMessage key={k} text={ev.text} />);
    else if (ev.kind === "tool_use")
      items.push(
        <ToolCallCard
          key={k}
          name={ev.name}
          input={ev.input}
          result={toolResults[ev.id]}
        />,
      );
    else if (ev.kind === "clear_marker") items.push(<ClearDivider key={k} />);
    else if (ev.kind === "compact_summary") items.push(<CompactDivider key={k} />);
  }

  for (const p of Object.values(props.permissions)) {
    items.push(
      <PermissionPromptCard
        key={`p-${p.id}`}
        id={p.id}
        kind={p.kind}
        target={p.target}
        resolved={p.resolved}
        onDecision={(d) => props.onDecision(p.id, d)}
      />,
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
        padding: "16px var(--pad-x) 12px",
      }}
    >
      {items}
    </div>
  );
}
