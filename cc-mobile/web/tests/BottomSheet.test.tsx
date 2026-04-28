import { fireEvent, render, screen } from "@testing-library/react";
import { BottomSheet } from "../src/components/BottomSheet";

test("renders children when open", () => {
  render(
    <BottomSheet open onClose={() => {}}>
      <div>contents</div>
    </BottomSheet>,
  );
  expect(screen.getByText("contents")).toBeInTheDocument();
});

test("hidden when closed", () => {
  const { container } = render(
    <BottomSheet open={false} onClose={() => {}}>
      <div>contents</div>
    </BottomSheet>,
  );
  // Sheet uses transform; check aria-hidden or absence of `open` class
  expect(container.querySelector(".sheet.open")).toBeNull();
});

test("calls onClose when backdrop clicked", () => {
  const onClose = vi.fn();
  render(
    <BottomSheet open onClose={onClose}>
      <div>contents</div>
    </BottomSheet>,
  );
  fireEvent.click(document.querySelector(".backdrop")!);
  expect(onClose).toHaveBeenCalled();
});
