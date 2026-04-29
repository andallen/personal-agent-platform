import { useEffect, useLayoutEffect, useState, useMemo, useRef } from "react";
import { TopBar } from "./components/TopBar";
import { MessageList } from "./components/messages/MessageList";
import { InputArea, type InputAreaHandle } from "./components/InputArea";
import { SlashPicker } from "./components/SlashPicker";
import { CompactingIndicator } from "./components/CompactingIndicator";
import { ThinkingIndicator } from "./components/ThinkingIndicator";
import { ModelSheet } from "./components/sheets/ModelSheet";
import { EffortSheet } from "./components/sheets/EffortSheet";
import { ModeSheet } from "./components/sheets/ModeSheet";
import { ProjectSheet } from "./components/sheets/ProjectSheet";
import { ResumeSheet } from "./components/sheets/ResumeSheet";
import { KebabSheet } from "./components/sheets/KebabSheet";
import { useWebSocket } from "./hooks/useWebSocket";
import { api } from "./api";
import type {
  AppState, Options, PermissionPrompt, Project,
  Session, SlashCommand,
} from "./types";

type SheetId = "project" | "mode" | "model" | "effort" | "kebab" | "resume" | null;
type Decision = "allow_once" | "allow_always" | "deny";

export default function ChatView() {
  const [state, setState] = useState<AppState | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [slashCmds, setSlashCmds] = useState<SlashCommand[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [openSheet, setOpenSheet] = useState<SheetId>(null);
  const [slashQuery, setSlashQuery] = useState("");
  const [generating, setGenerating] = useState(false);
  const [compacting, setCompacting] = useState(false);
  const [permissions, setPermissions] = useState<
    Record<string, PermissionPrompt & { resolved?: Decision }>
  >({});

  const inputRef = useRef<InputAreaHandle>(null);
  const slashCmdNames = useMemo(
    () => new Set(slashCmds.map((c) => c.name)),
    [slashCmds],
  );

  const compactTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  function startCompacting() {
    setCompacting(true);
    if (compactTimeout.current) clearTimeout(compactTimeout.current);
    // Safety: drop the indicator after 3 minutes even if we miss the
    // compact_summary signal (e.g. JSONL never gets the marker).
    compactTimeout.current = setTimeout(() => setCompacting(false), 180_000);
  }
  function stopCompacting() {
    setCompacting(false);
    if (compactTimeout.current) {
      clearTimeout(compactTimeout.current);
      compactTimeout.current = null;
    }
  }

  const { events: wsEvents, pushLocalClear } = useWebSocket("/ws");
  const [resuming, setResuming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);
  const didInitialScroll = useRef(false);

  useEffect(() => {
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      pinnedToBottom.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const hasContent = wsEvents.some((e) => e.kind === "chat_event");
    if (!didInitialScroll.current && hasContent) {
      el.scrollTop = el.scrollHeight;
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
        didInitialScroll.current = true;
        pinnedToBottom.current = true;
      });
      return;
    }
    if (pinnedToBottom.current) el.scrollTop = el.scrollHeight;
  }, [wsEvents, permissions, generating, compacting]);

  // When either indicator opens, its .bar grows from 0 → 24px via a CSS
  // height transition (~220ms). A one-shot scrollTop runs before the
  // transition starts, so the indicator ends up below the viewport and gets
  // hidden behind the input. Re-pin every animation frame for the full
  // transition window so the bottom tracks the growing content.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!compacting && !generating) return;
    let raf = 0;
    const start = performance.now();
    const tick = () => {
      el.scrollTop = el.scrollHeight;
      pinnedToBottom.current = true;
      if (performance.now() - start < 280) raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [compacting, generating]);

  useEffect(() => {
    for (const ev of wsEvents) {
      if (ev.kind === "state") setState(ev.state);
      else if (ev.kind === "permission_prompt")
        setPermissions((p) => ({ ...p, [ev.prompt.id]: ev.prompt }));
      else if (ev.kind === "permission_prompt_resolved")
        setPermissions((p) => {
          const cur = p[ev.id];
          if (!cur) return p;
          return { ...p, [ev.id]: { ...cur, resolved: cur.resolved ?? "allow_once" } };
        });
    }
    const last = wsEvents.at(-1);
    if (last?.kind === "chat_event") {
      const k = last.event.kind;
      if (k === "user_message") {
        const text = (last.event as { text?: string }).text ?? "";
        // Slash commands (/compact, /clear, /model, ...) are handled by CC
        // without producing an assistant_text turn, so don't enter the
        // generating state — it would never get cleared.
        if (!text.trim().startsWith("/")) setGenerating(true);
        else setGenerating(false);
        if (text.trim().startsWith("/compact")) startCompacting();
        // First chat event from the new session = resume completed.
        setResuming(false);
      }
      else if (k === "tool_use" || k === "tool_result") {
        setGenerating(true);
        setResuming(false);
      }
      else if (k === "assistant_text") {
        setGenerating(false);
        setResuming(false);
      }
      else if (k === "clear_marker") setGenerating(false);
      if (k === "compact_summary" || k === "clear_marker") stopCompacting();
    }
  }, [wsEvents]);

  useEffect(() => {
    api.getState().then(setState);
    api.options().then(setOptions);
    api.slashCommands().then(setSlashCmds);
    api.projects().then(setProjects);
  }, []);

  useEffect(() => {
    if (state?.cwd) api.sessions(state.cwd).then(setSessions);
  }, [state?.cwd]);

  function modelLabel(id: string | null) {
    if (!id) return "—";
    return options?.models.find((m) => m.id === id)?.label ?? id;
  }

  async function handleDecision(id: string, d: Decision) {
    await api.permission(id, d);
    setPermissions((p) => {
      const cur = p[id];
      if (!cur) return p;
      return { ...p, [id]: { ...cur, resolved: d } };
    });
  }

  async function handleAction(action: "resume" | "clear" | "compact") {
    setOpenSheet(action === "resume" ? "resume" : null);
    if (action === "clear") await api.clear();
    if (action === "compact") {
      startCompacting();
      await api.compact();
    }
  }

  const project = useMemo(() => state?.cwd.split("/").pop() ?? "(none)", [state]);

  if (!state || !options) return <div style={{ padding: 24 }}>loading…</div>;

  return (
    <div style={{ position: "relative", display: "flex", flexDirection: "column", height: "100dvh", maxWidth: 760, margin: "0 auto" }}>
      <TopBar
        project={project}
        mode={state.mode}
        model={modelLabel(state.model)}
        effort={state.effort ?? "—"}
        onOpen={(id) => setOpenSheet(id)}
      />
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", overflowX: "hidden", paddingBottom: "72px" }}>
        <MessageList events={wsEvents} permissions={permissions} onDecision={handleDecision} />
        {resuming && (
          <div style={{
            padding: "16px var(--pad-x)",
            color: "var(--c-fg-dim, #888)",
            fontStyle: "italic",
            textAlign: "center",
          }}>
            resuming session…
          </div>
        )}
        <CompactingIndicator open={compacting} />
        <ThinkingIndicator open={generating && !compacting} />
      </div>
      <SlashPicker
        open={slashQuery.startsWith("/")}
        query={slashQuery}
        commands={slashCmds}
        onPick={(name) => {
          inputRef.current?.replaceText(name);
          setSlashQuery("");
        }}
      />
      <InputArea
        ref={inputRef}
        commandNames={slashCmdNames}
        generating={generating || compacting}
        onSend={(t) => api.send(t)}
        onInterrupt={() => {
          setGenerating(false);
          stopCompacting();
          api.interrupt();
        }}
        onSlash={(q) => setSlashQuery(q)}
      />

      <ModelSheet
        open={openSheet === "model"}
        current={state.model}
        models={options.models}
        onPick={(id) => api.setModel(id)}
        onClose={() => setOpenSheet(null)}
      />
      <EffortSheet
        open={openSheet === "effort"}
        current={state.effort}
        efforts={options.efforts}
        onPick={(e) => api.setEffort(e)}
        onClose={() => setOpenSheet(null)}
      />
      <ModeSheet
        open={openSheet === "mode"}
        current={state.mode}
        modes={options.modes}
        onPick={(m) => api.setMode(m)}
        onClose={() => setOpenSheet(null)}
      />
      <ProjectSheet
        open={openSheet === "project"}
        current={state.cwd}
        projects={projects}
        onPick={(cwd) => api.switchProject(cwd)}
        onClose={() => setOpenSheet(null)}
      />
      <ResumeSheet
        open={openSheet === "resume"}
        sessions={sessions}
        onPick={(id) => {
          // Optimistic: drop a clear_marker locally so the prior session's
          // chat disappears the instant the user taps, and show the
          // "resuming…" indicator until the first event from the new
          // session arrives over the websocket. Without this, the UI sits
          // unchanged for the round-trip + tailer-poll window (~300ms+).
          pushLocalClear();
          setResuming(true);
          api.resume(id);
        }}
        onClose={() => setOpenSheet(null)}
      />
      <KebabSheet
        open={openSheet === "kebab"}
        onAction={handleAction}
        onClose={() => setOpenSheet(null)}
      />

    </div>
  );
}
