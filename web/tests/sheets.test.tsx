import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ModelSheet } from "../src/components/sheets/ModelSheet";

describe("ModelSheet", () => {
  it("calls onPick with id when option clicked", () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <ModelSheet
        open
        current="claude-opus-4-7"
        models={[
          { id: "claude-opus-4-7", label: "Opus 4.7" },
          { id: "claude-sonnet-4-6", label: "Sonnet 4.6" },
        ]}
        onPick={onPick}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByText("Sonnet 4.6"));
    expect(onPick).toHaveBeenCalledWith("claude-sonnet-4-6");
    expect(onClose).toHaveBeenCalled();
  });
});
