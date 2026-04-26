# cc-mobile research findings (2026-04-25)

CC version: 2.1.119  
Platform: Ubuntu Linux, Ryzen 5 2600  
Research method: tmux throwaway sessions + binary string analysis

---

## 1. "Auto mode"

Auto mode exists in CC v2.1.119 but it is NOT a user-selectable mode in the same sense as plan/default/acceptEdits. It is a classifier-based permission system where the auto-mode AI decides whether to allow tool calls without prompting.

- CLI command: `claude auto-mode` — inspects the classifier config
- Subcommands: `config`, `critique`, `defaults`
- `--permission-mode` flag accepts `auto` as a value (alongside `acceptEdits`, `bypassPermissions`, `default`, `dontAsk`, `plan`)
- In the UI, auto mode is NOT in the normal Shift+Tab cycle. The cycle is:  
  `bypass permissions → (default, no indicator) → accept edits → plan mode`
- The binary contains `useAutoModeDuringPlan` config and a gate check `isAutoModeGateEnabled()` suggesting it requires feature gating (may only be available to enterprise/specific users)
- There is an `opusplan` alias that means "Opus in plan mode, else Sonnet" — this is a model alias, not a separate mode

**Conclusion:** Drop "Auto mode" from the dropdown unless you want to expose the `--permission-mode auto` flag. In normal interactive use, the mode cycle is bypass / default / accept-edits / plan.

---

## 2. Slash-command syntax for setting model / effort / mode

All three use direct slash commands with the value as an argument. The TUI picker is bypassed by sending the complete command string.

- **Model:** `/model <name_or_alias>` e.g. `/model claude-sonnet-4-6` or `/model sonnet`
- **Effort:** `/effort <level>` where level is one of: `low`, `medium`, `high`, `xhigh`, `max`, `auto`
- **Mode:** Shift+Tab cycles modes interactively; no slash command for mode toggle.  
  Alternatively `/plan` enters plan mode; no slash command to exit (Shift+Tab to cycle out).

The binary shows `/model` has `argumentHint:"[model]"` (optional arg — omitting opens the picker). The thinClientDispatch is `"control-request"`, which means it sends directly rather than posting to the conversation. Same for `/effort`.

For the server, send: `tmux send-keys "/model claude-sonnet-4-6" Enter` — this works.

---

## 3. TUI signatures (permission prompt + plan approval)

### Bash permission prompt

**IMPORTANT:** On Andrew's rig, `~/.claude/settings.json` has `"permissions": {"allow": ["Bash", "Read", "Write", "Edit", ...]}` — a blanket allow for all standard tools. This means the bash permission prompt **will not appear** in a normal session on this rig unless a specific command matches the `"ask"` patterns (e.g., `rm -rf /`).

The `permission_bash.txt` fixture shows a bash command that ran WITHOUT a prompt (the global allow list fired). This is the expected state on Andrew's rig.

From binary source analysis, the bash permission dialog renders:
- Title: `"Bash command"` (or `"Bash command (unsandboxed)"` in sandbox mode)
- Shows the command being run
- `"Do you want to proceed?"`
- SelectInput options (see Section 4)

Distinguishing pattern for bash prompt: `Do you want to proceed?` + `Bash command` in the title box.

See: `server/tests/fixtures/pane/permission_bash.txt` (shows command that ran without prompt due to global allow list)

### Edit/Write permission prompt

The `permission_edit.txt` fixture (captured from an earlier session before settings were checked) shows a real Write permission prompt. It has the format:

```
 Create file
 research-test.txt
╌╌╌...╌╌╌
  1 hello
╌╌╌...╌╌╌
 Do you want to create research-test.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend
```

Distinguishing pattern for edit prompt: `Do you want to (create|edit|write)` + numbered `1. Yes` / `2. Yes, allow` / `3. No` menu.

See: `server/tests/fixtures/pane/permission_edit.txt`

### Plan approval gate

The plan fixture (`plan_approval.txt`) shows plan mode actively running (not the approval dialog, since the session ran through the writing-plans skill which does its own thing). The relevant approval dialogs extracted from binary source:

**Enter plan mode?** (when model requests to enter plan mode):
- Title: `"Enter plan mode?"`
- "Claude wants to enter plan mode to explore and design an implementation approach."
- Bulleted description of what plan mode does
- "No code changes will be made until you approve the plan."
- Buttons: `"Yes, enter plan mode"` / `"No, start implementing now"`

**Plan presented** (after plan is drafted):
- Shows `" User approved Claude's plan"` (with plan symbol ⏸)
- OR shows `" Plan submitted for team lead approval"` (for multi-agent workflows)

Distinguishing pattern for plan approval: `"Enter plan mode?"` title, or the ⏸ symbol in status bar with `"plan mode on"` footer text.

See: `server/tests/fixtures/pane/plan_approval.txt` (shows plan mode actively generating, not the approval gate itself)

---

## 4. Permission keystroke mapping

From the `permission_edit.txt` fixture (confirmed live capture), the permission menu is a numbered SelectInput:

```
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend
```

From binary source (the `hD4` function that builds options):
- `value:"yes"` → `option:{type:"accept-once"}` — allow this one time
- `value:"yes-session"` → `option:{type:"accept-session"}` — allow all in this session
- `value:"no"` → `option:{type:"reject"}` — deny

**Keystroke mapping:**
- **Allow once:** press `1` then Enter (or arrow to first item, Enter)
- **Allow for session:** press `2` then Enter (or Shift+Tab from first item, then Enter)
- **Deny:** press `3` then Enter (or `n` key)
- **Cancel:** `Escape`
- **Amend with instructions:** `Tab` enters text input on the Yes/No item

The "allow for session" label includes the path scope (e.g., "Yes, allow all edits in `src/` during this session (shift+tab)") — the directory name is variable.

For Bash permission prompts specifically, the dialog also shows "Do you want to proceed?" with similar Yes/Yes-session/No options.

The key to send from the server: `tmux send-keys -t <session> "1" Enter` for allow-once, `"2" Enter` for allow-session, `"3" Enter` for deny.

---

## 5. Models / efforts / modes lists

### Models

Source: binary string extraction (model alias → display name mapping in binary).  
Key models in CC v2.1.119 (from `rw`/`C9H` function in binary):

| API name | Display name | Alias |
|---|---|---|
| claude-opus-4-7 | Opus 4.7 (default on Max) | `opus` |
| claude-opus-4-6 | Opus 4.6 | — |
| claude-opus-4-1 | Opus 4.1 | — |
| claude-opus-4-0 | Opus 4 | — |
| claude-sonnet-4-6 | Sonnet 4.6 (default on Pro) | `sonnet` |
| claude-sonnet-4-5 | Sonnet 4.5 | — |
| claude-sonnet-4-0 | Sonnet 4 | — |
| claude-3-7-sonnet | Sonnet 3.7 | — |
| claude-3-5-sonnet | Sonnet 3.5 | — |
| claude-haiku-4-5 | Haiku 4.5 | `haiku` |
| claude-3-5-haiku | Haiku 3.5 | — |

Also: `opusplan` alias = "Opus in plan mode, else Sonnet". Not shown in normal model picker.  
The `/model` picker shows the aliases `sonnet`, `opus`, `haiku` + their current resolved names.

Discovery endpoint: CC fetches models from `/v1/models?beta=true` at runtime. The binary also has a `fallback-model` flag. The discovery list should be supplemented by this API call at startup.

### Efforts

From `--help` flag: `low, medium, high, xhigh, max`  
From `/effort` argumentHint: `[low|medium|high|xhigh|max|auto]` — `auto` is also accepted via the slash command but not via the CLI flag.

### Modes

From `--permission-mode` choices: `acceptEdits, auto, bypassPermissions, default, dontAsk, plan`  
In UI (Shift+Tab cycle order): `bypass permissions → (default) → accept edits → plan mode`

---

## 6. Slash command list source

**Built-in commands** (from binary analysis):
Core: `/clear`, `/compact`, `/config`, `/effort`, `/model`, `/resume`, `/plan`, `/help`, `/init`, `/memory`, `/status`, `/usage`, `/context`, `/diff`, `/theme`, `/permissions`, `/hooks`, `/keybindings`, `/tasks`, `/agents`, `/mcp`, `/plugin`, `/branch`, `/rename`, `/export`, `/copy`, `/commit`, `/review`, `/focus`, `/brief`, `/btw`

Full extracted list (~90 built-ins, including non-standard ones like `/heapdump`, `/bridge-kick`).

**User commands:** `~/.claude/commands/*.md` — none installed on this rig.

**Plugin commands:** `~/.claude/plugins/` — installed plugins (superpowers, frontend-design, ralph-wiggum, mockingbird). Plugin skills appear in the `/` picker filtered by the current project's enabled plugins.

**Plugin skills seen in picker:**
- `/writing-plans` (superpowers)
- `/brainstorming` (superpowers)
- `/subagent-driven-development` (superpowers)
- `/frontend-design` (frontend-design)

The picker only shows recently-used or matching commands when typed, not all at once.

**Merge order:** Built-ins → user commands (`~/.claude/commands/`) → plugin skills (enabled per project in `settings.json` `enabledPlugins`)

**Discovery approach for cc-mobile:** Use `claude --print "/skills"` or parse the pane after typing `/` — neither is robust. Best approach: maintain a static list of important built-ins + enumerate `~/.claude/commands/*.md` + `~/.claude/plugins/installed_plugins.json` for plugin skills.

---

## 7. JSONL granularity

**Per-message, not per-token.** Assistant text arrives as complete `assistant` messages with `message.content[]` blocks. Each block is of type `text`, `tool_use`, or `thinking`.

From sample session analysis (`server/tests/fixtures/jsonl/sample_session.jsonl`, 100 lines):
- Message types present: `assistant` (37), `user` (26), `system` (10), `attachment` (6+), `permission-mode` (8), `file-history-snapshot` (6), `last-prompt` (7)
- Content block types: `text` (13), `thinking` (10), `tool_use` (15), `tool_result` (15)
- User message `content` field can be a **string** (for slash command outputs, system context injections) or an **array of blocks** (for normal user messages)
- `permission-mode` record appears as the first line and also when mode changes
- `last-prompt` records the most recent user prompt (for display in resume)
- `attachment` records carry hook outputs, deferred tool names, skill listings

**Implication:** The JSONLTailer emits complete assistant messages. No streaming of partial text. Each `assistant` record contains the full response up to that point (or the incremental addition if the model adds more blocks). The tailer should track the last line it processed and only emit new lines.

Note: In v2.1.119, `alwaysThinkingEnabled: true` in settings means `thinking` blocks appear in `assistant` content. These should be skipped or optionally shown.

---

## 8. `claude --resume <id>`

**Arg form:** `claude --resume <session-id>` or `claude -r <session-id>`  
Session ID is the UUID filename (without `.jsonl`) of the JSONL file in `~/.claude/projects/<sanitized-cwd>/`.

**On valid ID:** Loads the full session history and drops into an interactive session with the context restored. Token count reflects the loaded history. Verified: `claude -r ab234838-d219-499d-9145-d9a2f9d1d244` from `/Users/andrewallen` CWD loaded correctly (58k tokens).

**CWD matters:** The session must be in the project matching the current CWD. Running `claude -r <id>` from a different directory fails with `"No conversation found with session ID: <id>"`.

**On invalid/nonexistent ID:** CC enters interactive mode with message:
```
No conversations found to resume.
Press Ctrl+C to exit and start a new conversation.
```
It does NOT exit — it waits for Ctrl+C. This means the server must detect this state and handle it (kill the session or send Ctrl+C).

**Additional flags:** `--fork-session` creates a new session ID instead of reusing the original.

---

## 9. `/clear` semantics

**Creates a NEW JSONL file.** `/clear` does not write a marker to the current JSONL; it starts a fresh session with a new UUID.

Verified: before `/clear`, session was `118963b1-....jsonl` (11 lines). After `/clear`, a new file `39dbc929-....jsonl` was created (6 lines). The old file is preserved on disk.

New JSONL starts with:
1. `file-history-snapshot` — snapshot of context state
2. `attachment` — `SessionStart:clear` hook success record
3. `attachment` — hook additional context
4. `user` — carries the `/clear` command context
5. `system` — `subtype: "local_command"`, `content: "<local-command-stdout></local-command-stdout>"`

**Implication:** JSONLTailer cannot rely on a single JSONL path. After `/clear`, it must detect the new file and switch to tailing it. The approach: watch the project directory for new `.jsonl` files, or check `ls -t` for a newer file after detecting stale tailing.

The `/clear` description from binary: `"Start a new session with empty context; previous session stays on disk (resumable with /resume)"`. Aliases: `reset`, `new`.

---

## Anything else surprising

1. **Global allow list prevents most permission prompts on this rig.** `~/.claude/settings.json` pre-allows `Bash`, `Read`, `Write`, `Edit`, `MultiEdit`, `Glob`, `Grep`, `LS`, `WebFetch`, `WebSearch`, `NotebookRead/Edit`, `TodoWrite`, `Task`, `Skill`, `mcp__*`. Permission prompts only appear for commands matching the `"ask"` list (e.g., `rm -rf /`, reads of `~/.ssh/id_*`). The cc-mobile permission prompt detector will be lightly exercised on this rig in normal use — the detector is still important for fresh installs or users with restrictive settings.

2. **Effort level "auto" exists** in the `/effort` command (argumentHint shows it) but NOT in `--help`. It selects effort automatically based on task complexity. Worth including in the dropdown with a note.

3. **`--resume` requires matching CWD.** The server must start claude from the correct project directory, not from a generic `/tmp` or the server's working directory. The `StateStore.last_cwd` must be used as the CWD when launching `claude -r <id>`.

4. **The binary is a compiled Bun executable** (ELF, 245MB), not Node.js. Strings extraction works but the JS is bundled/compiled — no clean JSON configs to parse for model lists or slash commands.

5. **Mode cycle order (BTab):** bypass → default (no indicator) → accept edits → plan mode → (wraps). The status bar footer shows the mode, e.g. `"⏸ plan mode on (shift+tab to cycle)"` or `"⏵⏵ bypass permissions on (shift+tab to cycle)"`. Default mode shows nothing in the footer.

6. **Stop hook errors visible in pane.** The `afplay /System/Library/Sounds/Glass.aiff` stop hook fails on Linux with `"Stop hook error: Failed with non-blocking status code: /bin/sh: 1: afplay: not found"`. This is benign but will appear in pane captures. The PaneWatcher should not treat this as a permission prompt.

7. **`permission-mode` JSONL records** appear at the start of each session and whenever mode changes. The `permissionMode` field values match `--permission-mode` choices: `bypassPermissions`, `default`, `plan`, `acceptEdits`, `dontAsk`, `auto`. This is how the JSONLTailer can know the current mode without parsing the pane.

8. **The `/resume` picker shows a search term.** `claude -r` without an ID opens an interactive fuzzy picker. `claude -r <partial-name>` filters it. For the server, always pass the full UUID.

9. **Plan mode in current CC (v2.1.119) with the `superpowers` plugin** triggers the `writing-plans` skill automatically, which runs extensive tool calls before producing the plan. The plan approval gate (confirm dialog) only appears when the model uses the `exit plan mode` tool. If the model never calls that tool (e.g., because it uses the writing-plans skill instead), no approval gate appears — the plan is just output as text.
