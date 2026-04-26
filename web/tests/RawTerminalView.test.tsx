import { render, screen } from "@testing-library/react";
import { RawTerminalView } from "../src/components/RawTerminalView";

test("renders pane content with monospace font", () => {
  render(<RawTerminalView paneText={"line1\nline2"} onClose={() => {}} />);
  expect(screen.getByText(/line1/)).toBeInTheDocument();
  const pre = screen.getByText(/line1/).closest("pre")!;
  expect(getComputedStyle(pre).fontFamily).toMatch(/mono|JetBrains/i);
});
