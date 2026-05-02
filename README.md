# Personal AI Agent Platform

A self-hosted AI agent setup running on a dedicated Ubuntu computer (Ryzen 5 2600, 16GB RAM, RTX 3060) that I can access from my phone. Two components: a mobile interface for Claude Code, and a pipeline that analyzed over 5,600 AI conversations and 1,300 Claude Code sessions to build a personalized tutoring system.

## How It Works

```
Phone (browser over private VPN / Tailscale)
        │
        ▼
Ubuntu Computer
├── cc-mobile ─── Mobile interface for Claude Code
│   ├── Python backend
│   │   ├── Keeps Claude running in a persistent terminal session (tmux)
│   │   ├── Watches Claude's log files for new output (JSONL tailing)
│   │   ├── Detects when Claude asks for permission to run something
│   │   ├── Coordinates everything and pushes updates to the phone
│   │   └── Stores session state (which project, which model, etc.)
│   └── React frontend
│       ├── Live-updating chat view over a persistent connection (WebSocket)
│       ├── Settings panels for model, effort level, and project
│       └── Inline permission and tool-use cards
│
└── tutor-extraction ─── Conversation analysis pipeline
    ├── Filtered 5,600+ conversations and 1,300 Claude Code sessions down to 3,002 with learning content
    ├── Ran 12 analysis scripts to find patterns (no AI needed, $0)
    ├── Used Claude's batch API to extract teaching insights ($33)
    └── Organized results into a 5-file tutoring skill for Claude Code
```

The workstation is only reachable through a private VPN (Tailscale) — nothing is exposed to the public internet. HTTPS certificates are handled automatically.

## Components

### cc-mobile — Phone Interface for Claude Code

Claude Code is a command-line AI tool that runs in a terminal. I was unsatisfied with the Claude Remote Control and other open-source options like CloudCLI so I built my own mobile-friendly web app to wrap its functionality.

Claude Code is an interactive terminal program, not a web service. It reads input from the keyboard and writes output to the screen. To put a web UI in front of it, the backend needs to:

1. Keep Claude running in a persistent terminal session (tmux) that survives disconnects so that Claude keeps running and I can reconnect even if the server crashes or I close my browser.
2. Read Claude's output by watching the structured log files it writes (JSONL format), rather than trying to parse the terminal display
3. Watch the terminal display for one specific thing: permission prompts (when Claude asks "can I run this command?"), because those don't appear in the log files
4. Forward everything to the phone over a persistent connection (WebSocket) that lets the server push updates in real time

**Features:**
- Dark-themed chat UI designed for phone screens
- Live-updating messages — output appears as Claude writes it
- Automatic reconnection if the connection drops (detects stale connections after 45 seconds of silence)
- `/` command picker with search-as-you-type
- Switch between Claude models (Opus, Sonnet, Haiku), effort levels, and operating modes
- Browse and resume previous sessions
- Switch between projects (different working directories)
- Permission prompts show up as tappable cards in the chat
- Tool calls (file edits, terminal commands) shown as collapsible cards
- Thinking and compacting progress indicators
- Stop button
- Runs as a background service (systemd) that starts automatically on boot

**Why build this instead of just SSHing in?** I still SSH in from my laptop, but from my phone it's much more convenient to have a mobile-friendly UI.

```
cc-mobile/
├── server/
│   ├── cc_mobile/
│   │   ├── api.py              # Web server and WebSocket endpoint
│   │   ├── session_manager.py  # Coordinates all backend components
│   │   ├── tmux_controller.py  # Manages the persistent terminal session
│   │   ├── jsonl_tailer.py     # Watches and parses Claude's log files
│   │   ├── pane_watcher.py     # Checks terminal for permission prompts
│   │   ├── detectors.py        # Pattern matching for permission/approval prompts
│   │   ├── event_bus.py        # Internal message routing between components
│   │   ├── options_discovery.py # Reads available models/modes from Claude at startup
│   │   ├── state_store.py      # Saves settings to disk (last project, model, etc.)
│   │   └── types.py            # Shared data structures
│   └── tests/                  # 64 tests
├── web/
│   ├── src/
│   │   ├── ChatView.tsx        # Main chat screen
│   │   ├── components/         # UI components (top bar, input, sheets, etc.)
│   │   ├── hooks/              # WebSocket connection with auto-reconnect
│   │   └── styles/             # Color palette and design tokens
│   └── tests/                  # 32 unit tests + end-to-end browser test
└── deploy/
    └── cc-mobile.service       # Service file for automatic startup
```

### tutor-extraction — Conversation Analysis Pipeline

I've had thousands of conversations with AI tools (ChatGPT, Claude, Gemini) over the past few years, many of them about learning math, CS, physics, finance, and philosophy. This pipeline processes those conversations to extract patterns in how I learn, then produces a set of instructions that tell Claude Code how to tutor me effectively.

**How the pipeline works:**

| Step | What happens | Result |
|------|-------------|--------|
| 1. Collect and filter | Gather conversations and Claude Code sessions from 6 sources, remove single-message chats, stock research templates, and non-learning content | 5,600+ conversations + 1,300 sessions → 3,002 with learning content |
| 2. Analyze without AI | Run sentiment analysis (VADER), topic clustering (TF-IDF), and pattern detection using traditional NLP — no API costs | 8 major learning behaviors identified, 9 topic threads spanning months, a map of how my interests evolved over time |
| 3. Compare models | Test different Claude models on sample conversations to find the best extraction quality | Sonnet selected after blind comparison across 4 rounds |
| 4. Extract at scale | Send all 3,002 conversations through Claude's batch API to identify learning moments | 5,177 learning patterns extracted at $33 total |
| 5. Synthesize | Group similar patterns (K-Means clustering), remove duplicates, and organize into teachable rules | 5-file skill system for the Claude app or Claude Code |

**The output: a tutoring skill for Claude/Claude Code**

The pipeline produced a set of instruction files that Claude loads when tutoring me. They encode specific patterns discovered across thousands of real conversations. The skill files are in `tutor-extraction/skill/`:

| File | When it's used |
|------|---------------|
| `SKILL.md` | Every tutoring session: covers communication style, how to handle my mental models, error correction, and calibrating to my knowledge level |
| `new-concept.md` | When introducing something I haven't seen before: let me build the analogy first, define every term on first use, plain language before formalism |
| `reasoning.md` | When I'm building or testing a mental model: give the rule then explain why it's true, manage overgeneralizations, let me find contradictions myself |
| `problem-solving.md` | When I'm working through problems: teach the strategy not just the answer, never give hints during attempts, match my pace |
| `feedback.md` | When reviewing my work: one correction at a time, be direct, use real Socratic questioning |

```
tutor-extraction/
├── scripts/
│   ├── preprocess_conversations.py     # Collects and filters all 6 conversation sources
│   ├── signal_experiment.py            # Scores conversations for learning content
│   ├── tfidf_clustering.py             # Groups conversations by topic
│   ├── cross_conversation_threading.py # Finds topic threads spanning months
│   ├── learning_style_deep_analysis.py # Identifies learning behavior patterns
│   ├── temporal_arc.py                 # Maps how interests evolved over time
│   ├── model_comparison.py             # Compares extraction quality across models
│   ├── extraction_prompt.txt           # The prompt used for batch extraction
│   └── ...                             # 12 scripts total
└── skill/                              # The output — tutoring instructions for Claude
    ├── SKILL.md
    ├── new-concept.md
    ├── reasoning.md
    ├── problem-solving.md
    └── feedback.md
```

## Tech Stack

| What | Technology |
|------|-----------|
| Backend | Python 3.12, FastAPI, WebSockets |
| Frontend | React 18, TypeScript, Vite |
| Process management | tmux, systemd |
| Log monitoring | watchfiles |
| Networking | Tailscale, HTTPS via Let's Encrypt |
| Server tests | pytest — 64 tests |
| Frontend tests | Vitest — 32 unit tests, Playwright — end-to-end test |
| Conversation analysis | Anthropic Batch API, scikit-learn |
| Package management | uv (for Python), npm (for JavaScript) |

## Design Decisions

| Decision | Why | What I tried first |
|----------|-----|--------------------|
| Build a custom mobile UI | Termius is a bad interface for Claude Code, and Claude Remote Control and Cloude CLI couldn't change models or effort levels | SSH via Termius, Claude Remote Control, CloudCLI |
| Read Claude's log files instead of scraping the terminal | Log files are structured data, so they won't break when Claude updates its UI. Terminal scraping is fragile. | Full terminal scraping |
| Only scrape the terminal for permission prompts | Permission prompts ("can I run this?") are the one thing that doesn't appear in log files | Ignoring them (bad UX), scraping everything (too fragile) |
| Keep Claude running in a persistent terminal using tmux | If the web server crashes or I close my browser, Claude keeps running and I can reconnect without losing work | Running Claude as a child process of the server (dies when server dies) |
| Use narrative extraction instead of structured JSON | Asking Claude to write free-form analysis of conversations captured richer insights than forcing it into rigid JSON fields | Structured output JSON schema |
| Sonnet over Haiku for extraction | Blind comparison showed Sonnet caught more subtle learning patterns, even though Haiku was cheaper | Haiku |
| Anthropic's batch API instead of running conversations through Claude Code | The batch API processes thousands of conversations in parallel at a 50% discount | Running them one at a time through Claude Code (~40/hour) |

## Testing

```bash
# Server tests (from cc-mobile/server/)
uv run pytest                    # 64 tests

# Frontend tests (from cc-mobile/web/)
npm test                         # 32 unit tests
npx playwright test              # End-to-end browser test

# All 97 tests pass
```

## Running

**Prerequisites:** Python 3.12+, Node.js 18+, tmux, Claude Code installed and authenticated.

```bash
# Start the backend
cd cc-mobile/server
uv sync
uv run python -m cc_mobile

# Start the frontend (development mode)
cd cc-mobile/web
npm install
npm run dev

# Build the frontend for production (backend serves it automatically)
npm run build

# Or run as a background service that starts on boot
cp cc-mobile/deploy/cc-mobile.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cc-mobile
```

Access from your phone at `https://<your-tailscale-hostname>:8767`.
