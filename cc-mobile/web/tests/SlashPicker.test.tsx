import { fireEvent, render, screen } from "@testing-library/react";
import { SlashPicker } from "../src/components/SlashPicker";

const cmds = [
  { name: "/clear", description: "reset" },
  { name: "/compact", description: "summarize" },
  { name: "/model", description: "switch model" },
];

test("filters by query", () => {
  render(<SlashPicker open query="/co" commands={cmds} onPick={() => {}} />);
  expect(screen.getByText("/compact")).toBeInTheDocument();
  expect(screen.queryByText("/clear")).toBeNull();
});

test("calls onPick on tap", () => {
  const onPick = vi.fn();
  render(<SlashPicker open query="/" commands={cmds} onPick={onPick} />);
  fireEvent.click(screen.getByText("/clear"));
  expect(onPick).toHaveBeenCalledWith("/clear");
});

test("closed renders nothing visible", () => {
  const { container } = render(
    <SlashPicker open={false} query="/" commands={cmds} onPick={() => {}} />,
  );
  expect(container.querySelector(".picker.open")).toBeNull();
});

test("no matches shows fallback", () => {
  render(<SlashPicker open query="/zzz" commands={cmds} onPick={() => {}} />);
  expect(screen.getByText(/no matches/i)).toBeInTheDocument();
});
