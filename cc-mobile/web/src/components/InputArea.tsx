import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import css from "./InputArea.module.css";

export function InputArea(props: {
  onSend: (text: string) => void;
  onInterrupt: () => void;
  onSlash: (query: string) => void;
  generating: boolean;
}) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, [text]);

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>) {
    const v = e.target.value;
    setText(v);
    if (v.startsWith("/")) props.onSlash(v);
    else props.onSlash("");
  }

  function send() {
    const trimmed = text.trim();
    if (!trimmed) return;
    props.onSend(trimmed);
    setText("");
  }

  return (
    <footer className={css.area}>
      <div className={css.row}>
        <textarea
          ref={taRef}
          aria-label="message"
          className={css.ta}
          rows={1}
          placeholder="message claude…"
          value={text}
          onChange={handleChange}
          autoComplete="off"
          autoCorrect="off"
        />
        {props.generating && (
          <button
            type="button"
            aria-label="interrupt"
            className={`${css.btn} ${css.interrupt}`}
            onClick={props.onInterrupt}
          >
            ■
          </button>
        )}
        <button
          type="button"
          aria-label="send"
          className={`${css.btn} ${css.send}`}
          onClick={send}
          disabled={!text.trim()}
        >
          ↑
        </button>
      </div>
    </footer>
  );
}
