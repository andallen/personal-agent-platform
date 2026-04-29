import type { ReactNode } from "react";
import css from "./BottomSheet.module.css";

export function BottomSheet(props: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  noScroll?: boolean;
}) {
  return (
    <>
      <div
        className={`backdrop ${css.backdrop} ${props.open ? "open " + css.open : ""}`}
        onClick={props.onClose}
      />
      <div
        className={`sheet ${css.sheet} ${props.open ? "open " + css.open : ""} ${props.noScroll ? css.noScroll : ""}`}
        role="dialog"
      >
        <div className={css.handle} />
        {props.children}
      </div>
    </>
  );
}
