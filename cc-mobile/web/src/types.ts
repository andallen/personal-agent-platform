export type ChatEvent =
  | { kind: "user_message"; text: string }
  | { kind: "assistant_text"; text: string }
  | { kind: "tool_use"; name: string; input: Record<string, unknown>; id: string }
  | { kind: "tool_result"; tool_use_id: string; content: string }
  | { kind: "clear_marker" }
  | { kind: "compact_summary" };

export type PermissionPrompt = {
  id: string;
  kind: "bash" | "edit" | "read" | "plan_approval" | "other";
  target: string;
  raw: string;
};

export type ServerEvent =
  | { kind: "chat_event"; event: ChatEvent }
  | { kind: "permission_prompt"; prompt: PermissionPrompt }
  | { kind: "permission_prompt_resolved"; id: string }
  | { kind: "state"; state: AppState }
  | { kind: "claude_started" }
  | { kind: "claude_died" };

export type AppState = {
  cwd: string;
  mode: string;
  model: string | null;
  effort: string | null;
  claude_alive: boolean;
};

export type Project = { cwd: string; name: string; mtime: number };
export type Session = { id: string; mtime: number; size: number; title: string | null };
export type Model = { id: string; label: string };
export type Options = { models: Model[]; efforts: string[]; modes: string[] };
export type SlashCommand = { name: string; description: string; kind?: "command" | "skill" };
