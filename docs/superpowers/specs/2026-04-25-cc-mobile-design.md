# cc-mobile — design spec

**Date:** 2026-04-25
**Owner:** andrew
**Status:** approved for plan-writing

A mobile-first web UI for Claude Code, served from the Ubuntu rig over Tailscale. Wraps the `claude` CLI running inside a persistent tmux session. Built to evolve with Claude Code rather than freeze its features at one moment in time.

---

## 1. Motivation

Existing options fail on different axes:

- **Termius / SSH** — claude renders in a phone terminal, but scrolling, tap targets, and keyboard ergonomics make it unusable for actually reading or replying.
- **cloudcli** (the previous third-party UI) — looked dated, did not surface controls users now expect (effort, mode, model), and broke as Claude Code evolved because it leaned on TUI output scraping.

Goal: a single page accessible from the phone over Tailscale that exposes Claude Code's real capability — not a dumbed-down chat — while staying maintainable as Claude Code releases new features.

---

## 2. Goals & non-goals

### Goals

- Read & reply to a live Claude Code session from a phone with first-class mobile UX.
- Expose the controls a phone user can't easily type: model, effort, mode, interrupt (Esc), `/clear`, `/compact`, project switch, resume, slash-command picker.
- Render the conversation as a chat with a terminal-influenced aesthetic (warm-dark palette, Claude coral accent, monospace for code) — not a literal terminal.
- Persist across SSH disconnects, server restarts, and reboots — claude keeps running on the rig regardless of what happens to the browser.
- Discover model/effort/mode options at runtime so dropdowns track Claude Code as it changes.
- Show tool calls (Bash / Edit / Read) as collapsed cards in the main flow; permission prompts as inline cards with tap-targets.

### Non-goals (v1)

- Image / photo / file attach (deferred).
- Quick snippets (deferred).
- Push notifications when claude finishes a task (deferred — service worker + web push).
- Multi-device sync of preferences (single user, single rig).
- A "new session" button — `/clear` covers the same intent.
- Showing assistant thinking blocks.
- Authentication beyond Tailscale tailnet membership.

---

## 3. Architecture

### Topology

```
phone (Safari / Chrome over Tailscale)
        │
        ▼
http://andrew-ms-7c02.tail3c0825.ts.net:<port>
        │
┌───────┴────────────────────────────────────────────┐
│                Ubuntu rig (andrew-MS-7C02)         │
│                                                    │
│  cc-mobile backend (Python, FastAPI)               │
│        │ ── reads ── ~/.claude/projects/<cwd>/*.jsonl
│        │ ── reads ── tmux capture-pane             │
│        │ ── writes ── tmux send-keys               │
│        ▼                                           │
│  tmux session "claude-mobile"                      │
│        │                                           │
│        ▼                                           │
│  claude  (the CLI, running in default mode by      │
│          default — last mode persisted)            │
└────────────────────────────────────────────────────┘
```

Everything runs on the rig. The phone reaches it only via Tailscale (no auth on top of the tailnet). Tmux is the durability layer: the claude process survives backend crashes, browser closes, and SSH disconnects.

### Hybrid output strategy

Claude Code's session JSONL files are the primary source for the conversation. They are already-structured events (user messages, assistant text, tool_use, tool_result), already evolve with Claude Code, and free us from the TUI-parsing treadmill that broke cloudcli.

Tmux pane capture is the **secondary** source, used only for narrowly-scoped detectors that recognise specific TUI states the JSONL doesn't carry — permission prompts and plan-mode approval gates. Each detector is one small function over a pane snapshot. Adding a new TUI state means adding one detector. The chat renderer never depends on pane parsing.

### Single writer

The backend is the only writer to tmux. The browser only talks to the backend. There is no path where two writers could race for the tmux pane.

---

## 4. Components

### 4.1 Backend (Python 3.12, FastAPI, single process)

**`TmuxController`** — owns the `claude-mobile` tmux session.
- `ensure_session()`, `start_claude(cwd, resume_id?, mode?)`, `kill_claude()`
- `send_text(text)`, `send_keys(*keys)` (e.g. `"Escape"`, `"Enter"`)
- `capture_pane(lines=200)` returns the last N lines of rendered pane text
- `is_claude_alive()` — checks pane content / process tree
- Wraps the `tmux` CLI via `subprocess`. No long-lived tmux library dependency.

**`JSONLTailer`** — locates and tails the active session jsonl in `~/.claude/projects/<encoded-cwd>/`.
- Polls the directory for the most recently modified `.jsonl`; reopens on change (e.g. claude restart writes a new one).
- Parses each new line, emits typed events: `UserMessage`, `AssistantText`, `ToolUse{name, input}`, `ToolResult{content}`, `ClearMarker`.
- Filters: thinking blocks, system reminders, slash-command metadata, ANSI escapes.
- Defensive: a malformed line is logged and skipped; never blocks the stream.

**`PaneWatcher`** — polls `tmux capture-pane` every ~250ms.
- Holds a list of `Detector` callables `(pane_text, prev_state) -> Optional[Event]`.
- Initial detectors:
  - `PermissionPromptDetector` — recognises CC's "Allow this …?" prompt shape; emits `PermissionPrompt{kind, target, raw}`.
  - `PlanApprovalDetector` — recognises plan-mode approval gate.
- Emits `_resolved` events when a previously-detected state goes away.
- Adding a new TUI state = adding one detector function + a snapshot fixture.

**`OptionsDiscovery`** — resolves available models / efforts / modes at runtime.
- Strategy: parse `claude --help` and `~/.claude.json` where possible; fall back to a hand-maintained list embedded in the code.
- Cached per process; refresh-on-demand via REST endpoint.
- Exposes `get_models()`, `get_efforts()`, `get_modes()`, `get_slash_commands()`.

**`StateStore`** — JSON file at `~/.config/cc-mobile/state.json`.
- Holds: `last_cwd`, `last_mode`, `last_model`, `last_effort`.
- Read on boot; written on every change; atomic write (`tmp + rename`).

**`SessionManager`** — orchestrator. Holds the other components and exposes intent-level methods.
- `boot()`, `send_user_message(text)`, `set_mode(value)`, `set_model(value)`, `set_effort(value)`, `interrupt()` (Esc), `clear()` (`/clear`), `compact()` (`/compact`), `resume(session_id)`, `switch_project(cwd)`, `list_recent_projects()`, `list_recent_sessions(cwd)`, `current_state()`, `decide_permission(prompt_id, decision)`.
- Translates intents into `tmux send-keys` sequences plus `StateStore` updates plus event-bus emissions.

**Event bus** — small in-process pub/sub. `JSONLTailer`, `PaneWatcher`, and `SessionManager` publish; the WebSocket route subscribes and forwards to connected clients.

**`api`** (FastAPI) — REST + WebSocket.

REST (one-shot actions):

| Method | Path                   | Body / Query        | Purpose                                                  |
| ------ | ---------------------- | ------------------- | -------------------------------------------------------- |
| GET    | `/api/state`           | —                   | current cwd, mode, model, effort, claude alive flag      |
| POST   | `/api/send`            | `{text}`            | send a user message                                      |
| POST   | `/api/interrupt`       | —                   | send Esc                                                 |
| POST   | `/api/mode`            | `{value}`           | switch mode                                              |
| POST   | `/api/model`           | `{value}`           | switch model                                             |
| POST   | `/api/effort`          | `{value}`           | switch effort                                            |
| POST   | `/api/permission`      | `{id, decision}`    | resolve a permission prompt                              |
| POST   | `/api/clear`           | —                   | run `/clear`                                             |
| POST   | `/api/compact`         | —                   | run `/compact`                                           |
| POST   | `/api/resume`          | `{session_id}`      | restart claude with `--resume`                           |
| POST   | `/api/project`         | `{cwd}`             | restart claude in a different cwd                        |
| GET    | `/api/projects`        | —                   | recent project dirs from `~/.claude/projects/`           |
| GET    | `/api/sessions`        | `?cwd=<>`           | resumable sessions in a project, with previews          |
| GET    | `/api/options`         | —                   | available models / efforts / modes (cached)              |
| GET    | `/api/slash-commands`  | —                   | built-ins + `~/.claude/commands/*.md` for typeahead      |
| GET    | `/api/pane`            | `?lines=<>`         | current pane snapshot for raw-terminal view              |

WebSocket `/ws` — server → client events:

| Event                          | Payload                                            |
| ------------------------------ | -------------------------------------------------- |
| `chat_event`                   | `{kind: "user"|"assistant_text"|"tool_use"|"tool_result"|"clear_marker", ...}` |
| `permission_prompt`            | `{id, kind, target, raw}`                          |
| `permission_prompt_resolved`   | `{id, decision}`                                   |
| `state`                        | `{cwd, mode, model, effort, claude_alive}`         |
| `claude_started` / `claude_died` | metadata                                          |
| `pane_snapshot`                | `{text}` — only when client subscribes via query   |

Client → server: heartbeat / subscribe-to-pane-snapshots only. All actions go via REST for clarity.

### 4.2 Frontend (React 18 + Vite + TypeScript, no UI framework)

**`ChatView`** — top-level page. Owns the `WebSocket`. Renders `TopBar`, `MessageList`, `InputArea`. Toggles to `RawTerminalView` via kebab.

**`TopBar`** (sticky) — pills for Project / Mode / Model / Effort, plus kebab. Pills tap to open bottom sheets.

**`MessageList`** — feed of typed events. Renderers per kind:
- `UserMessage` — right-aligned bubble
- `AssistantMessage` — full-width prose, markdown, code blocks, syntax highlight
- `ToolCallCard` — bash/edit/read; collapsed by default with a one-line summary; tap to expand
- `PermissionPromptCard` — Allow once / Allow always / Deny tap targets; greys out when resolved
- `ClearDivider` — for `/clear` markers

**`InputArea`** (fixed bottom) — auto-growing textarea. Send button at rest; interrupt button (Esc) shown when claude is generating. Typing `/` opens `SlashPicker`.

**`SlashPicker`** — bottom-sheet typeahead. Items from `/api/slash-commands`. Tap inserts into the textarea (cursor at end), does NOT send.

**`ProjectSwitcher`** / **`ResumePicker`** — bottom sheets. Lists from REST endpoints. Includes a manual-path entry on `ProjectSwitcher`.

**`RawTerminalView`** — full-screen toggle. Subscribes to `pane_snapshot` stream; renders monospace, ANSI-aware. Escape hatch only.

**Coupling rule:** only `ChatView` talks to the WebSocket. Everything else takes props.

### 4.3 Visual spec (locked from prototype at `/home/andrew/cc-mobile-prototype/`)

**Palette (dark, warm, academic)**

| Token              | Value                          | Use                                       |
| ------------------ | ------------------------------ | ----------------------------------------- |
| `--bg`             | `#1a1612`                      | page background                           |
| `--bg-soft`        | `#14110d`                      | code blocks, inset backgrounds            |
| `--surface`        | `#25201a`                      | top bar, cards, input row                 |
| `--surface-2`      | `#2c2620`                      | sheets, popovers                          |
| `--border`         | `#3a342c`                      | hard borders                              |
| `--border-soft`    | `#2a251f`                      | subtle dividers                           |
| `--text`           | `#ebe4d4`                      | primary text                              |
| `--text-muted`     | `#9c9386`                      | secondary text                            |
| `--text-dim`       | `#6a6055`                      | placeholders, captions                    |
| `--accent`         | `#d97757`                      | Claude coral — focus, send, links         |
| `--accent-soft`    | `rgba(217,119,87,0.14)`        | accent fills                              |
| `--accent-dim`     | `#a85838`                      | accent borders, pressed                   |
| `--warn`           | `#e3b577`                      | permission prompts, banners               |
| `--user-bg`        | `#2a221a`                      | user-message bubble                       |

Read-tool tag colour `#c4a87b` (muted gold). Edit-tool tag colour `#b09484` (dusty mauve). Bash uses `--accent`.

**Typography**

- Sans (UI + prose): **Geist** with system fallbacks. Body 16px, line-height 1.55.
- Mono (code, terminal, pills): **JetBrains Mono**. Code 12.5–13px, line-height 1.5.
- No mono for prose body — palette + monospace code carry the terminal vibe.
- Both bundled as woff2 subsets so the phone never depends on a system font.

**Layout**

- TopBar 56px sticky, blurred bg. Pills 30px tall, pill radius. Horizontal scroll on overflow.
- Chat full-bleed scroll. 14px horizontal padding; 12-14px gap between messages.
- InputArea sticky bottom; auto-grow textarea (max 6 lines); send button (↑) at rest, interrupt (■) when generating.
- Sheets rise from bottom, 18px top radius, 24px drag handle, max-height 75dvh.
- Slash picker max-height 50dvh.
- Touch targets ≥ 44×44.
- `viewport-fit=cover`, `safe-area-inset-*` everywhere.

**Motion**

- Sheet rise/fall: 240ms `cubic-bezier(.2,.8,.2,1)`.
- Pill state crossfade: 120ms.
- Message append: 80ms fade-in.
- No bounces, no springs.

**Removed / simplified**

- No green accents.
- No cool/blue tints. No radial gradients.
- No `cc v0.x` brand label — pills are the only top-bar content.
- Mode pill goes warn-tinted only when `mode === bypass`.

---

## 5. Data flow & key sequences

### Boot

**Cold (no tmux session):** `SessionManager.boot()` → `TmuxController.ensure_session()` creates `claude-mobile` → `StateStore.get()` returns `last_cwd=/Users/andrewallen, last_mode=default` on first run → `start_claude(cwd, mode=default)` writes the launch keystroke into the pane → `JSONLTailer` locates the new jsonl → `PaneWatcher` starts polling. Server emits `state`. Client renders empty top bar + chat.

**Warm (claude alive):** boot detects an alive `claude` in the pane → skip launch → `JSONLTailer` reads the existing jsonl from the top, emitting historical events. Client renders the full conversation. WebSocket reconnects work the same way (re-tail from start, client re-derives state).

### Send a message

`POST /api/send {text}` → `SessionManager.send_user_message` → `TmuxController.send_text(text)` then `send_keys("Enter")` → claude processes → JSONL grows → `JSONLTailer` emits `assistant_text` / `tool_use` / `tool_result` → WebSocket → `MessageList` renders incrementally (tool calls appear as they happen; prose appears when each text block completes).

### Interrupt (Esc)

`POST /api/interrupt` → `TmuxController.send_keys("Escape")`. No further server-side handling — claude's own behaviour (stop / send-already-queued-prompt) is observed via the next jsonl/pane changes. **NB:** must be Esc, not Ctrl+C — Ctrl+C kills the claude process.

### Mode / model / effort change

`POST /api/{mode|model|effort} {value}` → `SessionManager` resolves the corresponding slash command (e.g. `/model claude-sonnet-4-6`), sends it via `send_text + Enter`, **bypassing the TUI picker entirely** — the picker never appears. Wait for next jsonl/pane confirmation, then `StateStore.update(...)` and emit `state` event. Top bar pills update on event receipt, not optimistically — keeps UI in sync with truth.

### Permission prompt

`PaneWatcher` poll captures pane → `PermissionPromptDetector` matches the prompt shape, extracts command/path → emits `permission_prompt {id, kind, target, raw}` → WS → `MessageList` appends `PermissionPromptCard`. User taps Allow once → `POST /api/permission {id, decision: "allow_once"}` → `TmuxController.send_keys` with the corresponding keystroke. Pane updates → detector no longer matches → emits `permission_prompt_resolved {id, decision}` → card greys out with the recorded decision.

### Project switch / resume

`POST /api/project {cwd}` → `kill_claude()` → `StateStore.update(last_cwd)` → `start_claude(cwd, mode=last_mode)` → `JSONLTailer.restart()` finds the new project's most-recent jsonl → events stream. Resume flow is identical except `start_claude(..., resume_id=id)` and the targeted jsonl is the one being resumed.

### `/clear`

`POST /api/clear` → `send_text("/clear") + Enter`. Claude itself handles state. `JSONLTailer` continues on the same jsonl. UI shows a divider in `MessageList` keyed off the clear marker.

### Failure recovery

- **Claude exited inside tmux:** `PaneWatcher` detects empty/shell prompt → emits `claude_died` → client shows banner with [Restart] / [Raw Terminal]. Restart re-runs `start_claude` with last state.
- **Tmux session lost:** `TmuxController` health check (every few seconds) detects → recreates session, restarts claude, re-tails jsonl. Client gets `claude_started`; reconnects continue.
- **WebSocket disconnect:** client retries with backoff, shows "reconnecting…" pill. On reconnect, server replays full state from jsonl from start so client re-derives consistent UI.
- **JSONL parse error on a line:** log + skip; never block the stream.
- **PaneWatcher detector miss:** no event. User can manually tap Raw Terminal. Add a detector for the missed state later.

---

## 6. Persistent state on the rig

| Path                                            | Owner       | Lifetime              |
| ----------------------------------------------- | ----------- | --------------------- |
| tmux session `claude-mobile`                    | tmux        | survives reboot if linger=yes (already on) |
| `~/.config/cc-mobile/state.json`                | StateStore  | persistent            |
| `~/.claude/projects/<cwd>/<session>.jsonl`      | claude      | persistent (CC-managed) |
| `~/.config/systemd/user/cc-mobile.service`      | systemd     | persistent            |
| port `8767` (8765 is chatlog, 8766 is the visual prototype) | systemd unit | runtime |

The backend runs as a systemd user service, enabled with `WantedBy=default.target`, which combined with `linger=yes` on the user means it autostarts at boot.

---

## 7. Testing

### Backend

- **Unit:** `JSONLTailer` parser against fixtures in `tests/fixtures/jsonl/`. `PaneWatcher` detectors against text fixtures in `tests/fixtures/pane/`.
- **Integration:** spawn a real `claude --print "echo hi"`-style probe inside an isolated tmux session; exercise `TmuxController` round-trips; verify event emission end-to-end.
- **State machine:** `SessionManager` sequence tests — boot → send → receive → mode-switch → restart → resume — each transition asserts `StateStore` and event bus.
- **Linting/types:** `ruff check` + `pyright` clean.

### Frontend

- **Component:** Vitest + Testing Library on each component in isolation.
- **E2E:** Playwright with mobile-viewport profiles (iPhone 14, Pixel 7) against a mocked WebSocket. Verifies: send/receive round-trip, permission tap, slash-picker insert, sheet open/close, project switch.
- **Bundle budget:** Vite production build ≤ 200 KB gzipped. CI fails if exceeded.
- **Manual:** real iPhone over Tailscale before declaring v1 done.

### Definition of done (per task)

- All affected unit + integration tests pass.
- `tsc --noEmit` and `ruff` clean.
- Manual smoke on phone: open URL → message round-trip → mode switch → permission flow → resume → project switch → `/clear`.
- `cc-mobile.service` survives a reboot of the rig with no lost state.

---

## 8. Research-before-code (resolved during plan-writing)

These are small lookups but the plan depends on the answers. None of them are blockers for spec approval; they get done as the first step of the implementation plan.

1. **"Auto mode"** — confirm what it actually is in current Claude Code. If it does not exist, drop from the dropdown.
2. **Slash-command syntax** for setting model / effort / mode in one shot — exact strings to send via `tmux send-keys` (e.g. `/model claude-sonnet-4-6`) so the TUI picker is bypassed.
3. **TUI signatures** — capture real pane text for: a default-mode bash permission prompt, a default-mode edit permission prompt, a plan-mode approval gate. Save as snapshot fixtures.
4. **Permission keystroke mapping** — what does CC accept for Allow once / Allow always / Deny? Number keys, `y`/`n`, arrow + Enter — confirm.
5. **Models / efforts / modes lists** — discovery source. Parse `claude --help`? Read `~/.claude.json`? Confirm where each list lives, and the fallback list for when discovery fails.
6. **Slash-command list source** — built-ins (where do they live in CC?) + `~/.claude/commands/*.md` + plugin-provided commands (from `~/.claude.json` plugins). Merge order.
7. **JSONL granularity** — confirm assistant text blocks land per-block (not per-token). Affects whether we show partial assistant text or wait for full block.
8. **`claude --resume <id>` flow** — verify the arg form and behaviour on bad ID.
9. **`/clear` semantics** — does it write a marker line in jsonl, start a new jsonl, or just reset in-process state?

---

## 9. Risks & mitigations

| Risk                                                    | Mitigation                                                                                |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| TUI parser drift breaks permission detection            | Narrow scope (only permission/plan), snapshot-fixture tests, raw-terminal escape hatch    |
| JSONL format changes between CC versions                | Defensive parsing — unknown content blocks logged + skipped; stream never blocks          |
| Claude process dies inside tmux                         | Health check + auto-restart with last-used state; UI banner with explicit restart action  |
| WebSocket flakiness on mobile networks                  | Exponential-backoff reconnect; idempotent server-side replay on reconnect                 |
| Discovery (model/effort/mode lists) breaks on CC update | Hand-maintained fallback list; refresh-on-demand REST endpoint                            |

---

## 10. Open product decisions (non-blocking)

- **Push notifications when claude finishes a long task.** Skipping for v1; revisit after first real-use feedback.
- **Image / photo / file attach.** Punted per project scope — add later.
- **Quick snippets.** Punted per project scope.
- **Multi-device preference sync.** Out of scope; single-user, single-rig.

---

## 11. References

- Visual prototype: `/home/andrew/cc-mobile-prototype/index.html` (served as `cc-mobile-proto.service`, port 8766)
- Existing chatlog viewer (different project, kept as reference): `/home/andrew/chatlog/server.py` (`chatlog.service`, port 8765)
- Claude Code session jsonls: `~/.claude/projects/-Users-andrewallen/*.jsonl`
- Tailscale rig hostname: `andrew-ms-7c02.tail3c0825.ts.net` (IPv4: `100.77.233.38`)
