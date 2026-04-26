import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TopBar } from "../src/components/TopBar";

describe("TopBar", () => {
  it("clicking model pill calls onOpen('model')", () => {
    const onOpen = vi.fn();
    render(
      <TopBar
        project="andrewallen"
        mode="default"
        model="opus 4.7"
        effort="high"
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByLabelText("model"));
    expect(onOpen).toHaveBeenCalledWith("model");
  });

  it("warn class only on bypass mode", () => {
    const { rerender, container } = render(
      <TopBar
        project="x"
        mode="default"
        model="m"
        effort="e"
        onOpen={() => {}}
      />,
    );
    let modeButton = container.querySelector(`button[aria-label="mode"]`) as HTMLElement | null;
    expect(modeButton?.className).not.toContain("warn");

    rerender(
      <TopBar project="x" mode="bypass" model="m" effort="e" onOpen={() => {}} />,
    );
    modeButton = container.querySelector(`button[aria-label="mode"]`) as HTMLElement | null;
    expect(modeButton?.className).toContain("warn");
  });
});
