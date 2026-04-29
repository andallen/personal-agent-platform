import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InputArea } from "../src/components/InputArea";

test("send button disabled when empty", () => {
  render(<InputArea onSend={() => {}} onInterrupt={() => {}} onSlash={() => {}} generating={false} commandNames={new Set()} />);
  const send = screen.getByLabelText("send") as HTMLButtonElement;
  expect(send.disabled).toBe(true);
});

test("typing enables send and onSend fires", async () => {
  const onSend = vi.fn();
  render(<InputArea onSend={onSend} onInterrupt={() => {}} onSlash={() => {}} generating={false} commandNames={new Set()} />);
  const ta = screen.getByLabelText("message") as HTMLTextAreaElement;
  await userEvent.type(ta, "hi");
  fireEvent.click(screen.getByLabelText("send"));
  expect(onSend).toHaveBeenCalledWith("hi");
});

test("interrupt button visible when generating, calls onInterrupt", () => {
  const onInterrupt = vi.fn();
  render(<InputArea onSend={() => {}} onInterrupt={onInterrupt} onSlash={() => {}} generating commandNames={new Set()} />);
  fireEvent.click(screen.getByLabelText("interrupt"));
  expect(onInterrupt).toHaveBeenCalled();
});

test("typing / triggers onSlash with current value", async () => {
  const onSlash = vi.fn();
  render(<InputArea onSend={() => {}} onInterrupt={() => {}} onSlash={onSlash} generating={false} commandNames={new Set()} />);
  const ta = screen.getByLabelText("message");
  await userEvent.type(ta, "/cl");
  expect(onSlash).toHaveBeenLastCalledWith("/cl");
});
