import type {
  AppState,
  Options,
  Project,
  Session,
  SlashCommand,
} from "./types";

const json = (path: string, init?: RequestInit) =>
  fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  }).then(async (r) => {
    if (!r.ok) throw new Error(`http ${r.status}`);
    return r.json();
  });

export const api = {
  getState: (): Promise<AppState> => json("/api/state"),
  send: (text: string) =>
    json("/api/send", { method: "POST", body: JSON.stringify({ text }) }),
  interrupt: () => json("/api/interrupt", { method: "POST" }),
  setMode: (value: string) =>
    json("/api/mode", { method: "POST", body: JSON.stringify({ value }) }),
  setModel: (value: string) =>
    json("/api/model", { method: "POST", body: JSON.stringify({ value }) }),
  setEffort: (value: string) =>
    json("/api/effort", { method: "POST", body: JSON.stringify({ value }) }),
  clear: () => json("/api/clear", { method: "POST" }),
  compact: () => json("/api/compact", { method: "POST" }),
  resume: (session_id: string) =>
    json("/api/resume", { method: "POST", body: JSON.stringify({ session_id }) }),
  switchProject: (cwd: string) =>
    json("/api/project", { method: "POST", body: JSON.stringify({ cwd }) }),
  permission: (id: string, decision: "allow_once" | "allow_always" | "deny") =>
    json("/api/permission", {
      method: "POST",
      body: JSON.stringify({ id, decision }),
    }),
  projects: (): Promise<Project[]> => json("/api/projects"),
  sessions: (cwd: string): Promise<Session[]> =>
    json(`/api/sessions?cwd=${encodeURIComponent(cwd)}`),
  options: (): Promise<Options> => json("/api/options"),
  slashCommands: (): Promise<SlashCommand[]> => json("/api/slash-commands"),
};
