import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { ChangeEvent, UIEvent } from "react";
import css from "./InputArea.module.css";

export type InputAreaHandle = {
  replaceText: (text: string) => void;
};

type Props = {
  onSend: (text: string) => void;
  onInterrupt: () => void;
  onSlash: (query: string) => void;
  generating: boolean;
  commandNames: Set<string>;
};

export const InputArea = forwardRef<InputAreaHandle, Props>(function InputArea(props, ref) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, [text]);

  useImperativeHandle(ref, () => ({
    replaceText(newText: string) {
      // Replace just the trailing slash token (what the user typed so far) —
      // preserves any preamble text. Same path for commands and skills.
      setText((cur) => {
        const m = /\s\S*$/.exec(cur);
        const tokenStart = m ? m.index + 1 : 0;
        const lastToken = cur.slice(tokenStart);
        if (!lastToken.startsWith("/")) return cur;
        return cur.slice(0, tokenStart) + newText;
      });
      props.onSlash("");
    },
  }), [props.onSlash]);

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>) {
    const v = e.target.value;
    setText(v);
    const lastToken = v.split(/\s+/).pop() ?? "";
    if (lastToken.startsWith("/") && lastToken.length > 0) props.onSlash(lastToken);
    else props.onSlash("");
  }

  function handleScroll(e: UIEvent<HTMLTextAreaElement>) {
    if (backdropRef.current) {
      backdropRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  }

  function send() {
    const trimmed = text.trim();
    if (!trimmed) return;
    props.onSend(trimmed);
    setText("");
  }

  // Split into runs of whitespace and non-whitespace; mark non-whitespace
  // runs that exactly match a known slash command. The backdrop layer renders
  // these runs in faded blue while everything else stays default — the
  // textarea itself is transparent on top and just provides the editor.
  const runs = useMemo(() => {
    const parts = text.split(/(\s+)/);
    return parts.map((p) => ({
      text: p,
      cmd: p.length > 0 && !/^\s+$/.test(p) && props.commandNames.has(p),
    }));
  }, [text, props.commandNames]);

  return (
    <footer className={css.area}>
      <div className={css.row}>
        <div className={css.taWrap}>
          <div className={css.backdrop} ref={backdropRef} aria-hidden="true">
            {runs.map((r, i) =>
              r.cmd ? (
                <span key={i} className={css.cmd}>{r.text}</span>
              ) : (
                <span key={i}>{r.text}</span>
              )
            )}
            {"\n"}
          </div>
          <textarea
            ref={taRef}
            aria-label="message"
            className={css.ta}
            rows={1}
            placeholder="message claude…"
            value={text}
            onChange={handleChange}
            onScroll={handleScroll}
            autoComplete="off"
            autoCorrect="off"
          />
        </div>
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
          disabled={!text.trim() || props.generating}
        >
          ↑
        </button>
      </div>
    </footer>
  );
});
