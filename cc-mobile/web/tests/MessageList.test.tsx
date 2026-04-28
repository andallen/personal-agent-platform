import { render, screen } from "@testing-library/react";
import { MessageList } from "../src/components/messages/MessageList";
import type { ServerEvent } from "../src/types";

test("renders user → assistant → tool sequence", () => {
  const events: ServerEvent[] = [
    { kind: "chat_event", event: { kind: "user_message", text: "ping" } },
    { kind: "chat_event", event: { kind: "assistant_text", text: "pong" } },
    {
      kind: "chat_event",
      event: { kind: "tool_use", id: "t1", name: "Bash", input: { command: "ls" } },
    },
    {
      kind: "chat_event",
      event: { kind: "tool_result", tool_use_id: "t1", content: "f1\nf2" },
    },
  ];
  render(<MessageList events={events} permissions={{}} onDecision={() => {}} />);
  expect(screen.getByText("ping")).toBeInTheDocument();
  expect(screen.getByText("pong")).toBeInTheDocument();
  expect(screen.getByText(/ls/)).toBeInTheDocument();
});

test("renders permission prompt", () => {
  render(
    <MessageList
      events={[]}
      permissions={{
        p1: { id: "p1", kind: "bash", target: "rm /tmp/x", raw: "..." },
      }}
      onDecision={() => {}}
    />,
  );
  expect(screen.getByText("rm /tmp/x")).toBeInTheDocument();
  expect(screen.getByText("Allow once")).toBeInTheDocument();
});

test("renders clear divider", () => {
  render(
    <MessageList
      events={[{ kind: "chat_event", event: { kind: "clear_marker" } }]}
      permissions={{}}
      onDecision={() => {}}
    />,
  );
  expect(screen.getByText(/cleared/i)).toBeInTheDocument();
});
