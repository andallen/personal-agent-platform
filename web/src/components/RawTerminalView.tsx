export function RawTerminalView(props: { paneText: string; onClose: () => void }) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "var(--bg-soft)", color: "var(--text)",
        overflow: "auto", padding: "16px",
      }}
    >
      <button
        onClick={props.onClose}
        style={{
          position: "fixed", top: "calc(env(safe-area-inset-top) + 12px)",
          right: 12, background: "var(--surface)", color: "var(--text)",
          border: "1px solid var(--border)", padding: "6px 10px",
          borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 12,
        }}
      >
        close
      </button>
      <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, whiteSpace: "pre", margin: 0 }}>
        {props.paneText}
      </pre>
    </div>
  );
}
