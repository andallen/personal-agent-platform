import { useEffect, useState, useMemo } from "react";
import { TopBar } from "./components/TopBar";
import { MessageList } from "./components/messages/MessageList";
import { InputArea } from "./components/InputArea";
import { SlashPicker } from "./components/SlashPicker";
import { RawTerminalView } from "./components/RawTerminalView";
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
  const [rawOpen, setRawOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [permissions, setPermissions] = useState<
    Record<string, PermissionPrompt & { resolved?: Decision }>
  >({});

  const { events: wsEvents } = useWebSocket("/ws");

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
      if (last.event.kind === "tool_use") setGenerating(true);
      if (last.event.kind === "assistant_text") setGenerating(false);
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

  async function handleAction(action: "resume" | "clear" | "compact" | "raw") {
    if (action === "clear") await api.clear();
    if (action === "compact") await api.compact();
    if (action === "resume") setOpenSheet("resume");
    if (action === "raw") setRawOpen(true);
  }

  const project = useMemo(() => state?.cwd.split("/").pop() ?? "(none)", [state]);

  if (!state || !options) return <div style={{ padding: 24 }}>loading…</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100dvh", maxWidth: 760, margin: "0 auto" }}>
      <TopBar
        project={project}
        mode={state.mode}
        model={modelLabel(state.model)}
        effort={state.effort ?? "—"}
        onOpen={(id) => setOpenSheet(id)}
      />
      <div style={{ flex: 1, overflowY: "auto" }}>
        <MessageList events={wsEvents} permissions={permissions} onDecision={handleDecision} />
      </div>
      <InputArea
        generating={generating}
        onSend={(t) => api.send(t)}
        onInterrupt={() => api.interrupt()}
        onSlash={(q) => setSlashQuery(q)}
      />

      <SlashPicker
        open={slashQuery.startsWith("/")}
        query={slashQuery}
        commands={slashCmds}
        onPick={(name) => setSlashQuery(name + " ")}
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
        onPick={(id) => api.resume(id)}
        onClose={() => setOpenSheet(null)}
      />
      <KebabSheet
        open={openSheet === "kebab"}
        onAction={handleAction}
        onClose={() => setOpenSheet(null)}
      />

      {rawOpen && <RawTerminalView paneText={"loading…"} onClose={() => setRawOpen(false)} />}
    </div>
  );
}
