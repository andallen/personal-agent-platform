import { fireEvent, render, screen } from "@testing-library/react";
import { UserMessage } from "../src/components/messages/UserMessage";
import { AssistantMessage } from "../src/components/messages/AssistantMessage";
import { ToolCallCard } from "../src/components/messages/ToolCallCard";
import { PermissionPromptCard } from "../src/components/messages/PermissionPromptCard";
import { ClearDivider } from "../src/components/messages/ClearDivider";

test("UserMessage renders text", () => {
  render(<UserMessage text="hi there" />);
  expect(screen.getByText("hi there")).toBeInTheDocument();
});

test("AssistantMessage renders markdown bullets", () => {
  render(<AssistantMessage text={"- one\n- two\n"} />);
  expect(screen.getByText("one")).toBeInTheDocument();
  expect(screen.getByText("two")).toBeInTheDocument();
});

test("AssistantMessage renders code block", () => {
  render(<AssistantMessage text={"```js\nconst x = 1;\n```"} />);
  expect(screen.getByText(/const x = 1/)).toBeInTheDocument();
});

test("ToolCallCard collapsed shows summary", () => {
  render(
    <ToolCallCard name="Bash" input={{ command: "ls -la" }} result="file1\nfile2" />,
  );
  expect(screen.getByText(/bash/)).toBeInTheDocument();
  expect(screen.getByText(/ls -la/)).toBeInTheDocument();
});

test("ToolCallCard expand shows result", () => {
  render(
    <ToolCallCard name="Bash" input={{ command: "ls" }} result="OUTPUT_LINE" />,
  );
  fireEvent.click(screen.getByRole("button"));
  expect(screen.getByText(/OUTPUT_LINE/)).toBeInTheDocument();
});

test("PermissionPromptCard fires onDecision with allow_once", () => {
  const onDecision = vi.fn();
  render(
    <PermissionPromptCard
      id="p1"
      kind="bash"
      target="rm -rf /tmp/foo"
      onDecision={onDecision}
    />,
  );
  fireEvent.click(screen.getByText("Allow once"));
  expect(onDecision).toHaveBeenCalledWith("allow_once");
});

test("PermissionPromptCard resolved hides actions", () => {
  render(
    <PermissionPromptCard
      id="p1"
      kind="bash"
      target="rm /tmp/foo"
      resolved="allow_once"
      onDecision={() => {}}
    />,
  );
  expect(screen.queryByText("Allow once")).toBeNull();
  expect(screen.getByText(/allowed once/i)).toBeInTheDocument();
});

test("ClearDivider renders", () => {
  render(<ClearDivider />);
  expect(screen.getByText(/cleared/i)).toBeInTheDocument();
});
