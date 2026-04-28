# Personal AI Agent Platform — Progress Log

Self-hosted personal AI infrastructure running on a dedicated Ubuntu workstation (Ryzen 5 2600, 16GB RAM, RTX 3060), accessible remotely via Tailscale. Multiple components: mobile UI, knowledge base, learning pattern extraction.

## Project Components

### 1. cc-mobile — Phone-Accessible Claude Code UI
**Location:** `/home/andrew/cc-mobile/` (Ubuntu rig)
**Status:** Shipped and running

FastAPI + React web app serving a mobile-optimized UI for Claude Code over Tailscale HTTPS. Wraps `claude` CLI in a persistent tmux session; hybrid output strategy (JSONL primary + tmux pane scraping for permission/plan-approval prompts). Runs as systemd user service `cc-mobile.service` on port 8767.

**Features shipped:**
- Dark mode terminal-aesthetic mobile UI (warm academic palette, not neon)
- Chat input with `/` command and skill picker
- Chat history display with session resume
- Stop button (sends ESC to tmux process)
- Compacting indicator with scroll-to-bottom
- Thinking indicator (three dots)
- Auto-start Claude process on app open
- Tailscale-issued Let's Encrypt HTTPS cert

**Build sessions (from Claude Code export):**
- `908f99c7` (rig-side, ~52 user msgs) — initial concept + build: explored remote control, server mode, decided to build custom UI from scratch
- `276b446f` (Mac-side, ~41 msgs, 4 continuation files) — design brainstorm, frontend-design skill invocation, spec writing, implementation
- `e1943962` (Mac-side, ~56 msgs) — feature iteration: command picker, compact indicator, stop behavior, input bar fixes
- `76a0ae14` (Mac-side, ~31 msgs) — debugging: blank chat history, scroll position, thinking indicator, session resume showing UUIDs

### 2. Project Aristotle — Knowledge Base Pipeline
**Location:** `/home/andrew/projects/personal-kb/` (rig), synced copy at `~/projects/personal-kb/` (Mac)
**Status:** Pipeline complete. Being absorbed as a component of the agent platform.

Entity-centric knowledge base built from 1.5+ years of AI conversation history. SQLite + FTS5 storage with temperature-based attention system.

**What was built:**
- 4 data parsers: Claude, Gemini, YouTube, ChatGPT (`scripts/`)
- Full extraction pipeline: config, db, temperature, merger, extraction, entity_matching, synthesis, youtube, snapshots, main (`pipeline/`)
- Entity deduplication system (`pipeline/dedup.py`) — LLM-assisted clustering with human confirmation
- CLAUDE.md agent identity file with pedagogy, heartbeat, and kb-query skills
- Architecture decisions document (`docs/architecture-decisions.md`)

**Data processed:**
- 970 conversations (Claude + Gemini) processed chronologically
- ~$4 total API cost (Gemini Flash for extraction, Gemini Pro for synthesis)
- 2,462 raw entities → 1,336 after deduplication (46% reduction, 28 merge batches)

**Final DB stats:**
- 1,336 entities
- 20,775 timeline events
- 3,170 connections
- 5,605 processing log entries

**Key architecture decisions:**
- Entity-centric over chronological/time-period/markdown-profile alternatives
- Temperature system: exponential decay, 30-day half-life, memory vs. attention distinction
- Per-conversation extraction + count-based synthesis (every ~18 conversations)
- YouTube as passive heat modulation layer (never creates entities)
- Two-layer architecture: seed pipeline (Layer 1) + agent deep-reading (Layer 2)

### 3. Learning Pattern Extraction (The Tutor) — IN PROGRESS
**Location:** `~/ai-exports/` (source data), `~/tutor-extraction/` (working dir)
**Status:** Design phase

Extract learning patterns from ~3,800+ AI chats across 6 export sources to produce a CLAUDE.md that powers a personal tutor.

**Data sources (6):**
| Source | Conversations | Text size |
|---|---|---|
| ChatGPT (Feb export) | 2,000 | ~76 MB JSON |
| Claude acc1 (Feb) | 80 | 2.7 MB |
| Claude acc2 (Feb) | 115 | 13 MB |
| Claude (April) | 234 | 14 MB |
| Claude Code (April) | 1,385 sessions | ~800 MB JSONL |
| Gemini (Google Takeout, Apr 2025 – Apr 2026) | TBD | 15 MB text |

**Design decisions locked in (2026-04-27):**
1. **Signal categories:** All 5 — learning process, friction/resonance moments, effective/ineffective AI behaviors, domain knowledge map, misconception patterns
2. **Triage strategy:** Option C — cheap classifier sorts priority queue, but every conversation still gets full extraction. No gating = no silent information loss.
3. **Output format:** Hybrid — abstract observations anchored to verbatim evidence. Compact CLAUDE.md core + searchable evidence appendix. Audit trail from every rule back to the source chat.
4. **Execution model:** Iterate extraction prompt in Claude Code (subscription), production run via API Batch
5. **Cost reduction:** Programmatic filters first (drop 1-2 msg convos, keyword title triage), Haiku for classification + low-priority extraction, Sonnet for high-priority. Estimated $35–60 with caching + batch discount.

**Programmatic filter analysis (not yet applied):**
- 636 conversations have 1-2 messages — safe to drop (17% of corpus)
- All ChatGPT conversations have titles — useful for keyword-based priority sorting
- Claude conversations have titles for ~85%
- Claude Code sessions: need to filter by human/assistant message count, strip tool I/O noise

### 4. Infrastructure
**Hardware:** Ryzen 5 2600, 16GB RAM, RTX 3060, Ubuntu
**Network:** Tailscale VPN for remote access from Mac + phone
**Services:** cc-mobile.service (systemd user service, port 8767)
**Access methods:** SSH (`ssh andrew@100.77.233.38`), cc-mobile web UI, Claude Remote Control
**Syncing:** Syncthing between Mac and rig (personal-kb, Claude Code config)

---

## Timeline

### Feb 2026
- Exported all AI chat data (Claude x2, Gemini, YouTube)
- Built all 4 parsers (Claude, Gemini, YouTube, ChatGPT)
- Normalized data to unified JSON schema
- Designed entity-centric KB architecture (rejected alternatives: markdown profiles, chronological ledger, time-period layers)

### Mar 2026
- Full pipeline run: 970 conversations → 2,462 entities, ~$4 API cost
- Entity deduplication: 2,462 → 1,336 entities (28 merge batches)
- Built dedup.py for LLM-assisted automated clustering
- Pipeline declared complete

### Apr 2026 (early)
- Built cc-mobile: FastAPI + React, systemd service, Tailscale HTTPS
- Iterated on UI: command picker, compact indicator, thinking dots, stop button
- Debugged: chat history loading, scroll position, session resume
- cc-mobile declared shipped and running

### Apr 2026 (late — current)
- Exported fresh AI data (ChatGPT, Claude April, Claude Code sessions, Google Takeout April)
- Reframed Aristotle as a component, agent platform as the headline project
- Began learning pattern extraction design (the tutor)
- Locked in 5 design decisions for extraction pipeline
- Analyzed corpus: ~3,800+ conversations across 6 sources, ~125 MB text

---

## Decisions Log

| Date | Decision | Why | Alternatives rejected |
|---|---|---|---|
| 2026-02-28 | Entity-centric KB over alternatives | Mirrors intellectual development; single-interest trajectories queryable; connections first-class | Markdown profiles, chronological ledger, time-period layers |
| 2026-02-28 | SQLite over Postgres | Single-user, low write freq, zero infrastructure, FTS5 built in | Postgres + pgvector (overkill) |
| 2026-02-28 | Gemini Flash/Pro over Claude API | Single API key, cheap ($4 total), sufficient quality for extraction | Claude API (more expensive, two providers) |
| 2026-02-28 | Count-based synthesis (every ~18 convos) | Ensures meaningful material per pass regardless of density | Time-based (arbitrary boundaries) |
| 2026-03 | Temperature: 30-day half-life | Balances recency with memory; single mention dormant after ~47 days | Fixed decay rates, no decay |
| 2026-04 | Build custom cc-mobile UI | Claude Remote Control too limited (can't change model, limited affordances) | Remote Control, Termius SSH, Claude Cloud CLI |
| 2026-04 | Absorb Aristotle into agent platform | One headline project, Aristotle is a component (memory layer) not the whole story | Separate projects |
| 2026-04-27 | Tutor extraction: all 5 signal categories | Maximize learning signal captured | Subset of categories |
| 2026-04-27 | Tutor: Option C triage (sort, don't gate) | Preserves full coverage guarantee; no silent misclassification | Option A (no sort), Option B (gate by classifier) |
| 2026-04-27 | Tutor: hybrid abstract + verbatim output | Tutor gets rules AND examples; audit trail | Abstract-only (lossy), verbatim-heavy (floods CLAUDE.md) |
| 2026-04-27 | Tutor: Haiku/Sonnet tiering + programmatic filters | Keeps API cost under $60 vs $100-200 all-Sonnet | All-Sonnet (expensive), all-Haiku (lower quality on high-signal chats) |

---

## How to Update This File

After each work session that advances the project:
1. Add a dated entry under Timeline with what was built/decided/shipped
2. Add any new architectural decisions to the Decisions Log
3. Update component status if it changed
4. If a component ships a measurable outcome (entity count, cost, latency, etc.), record the number — these become resume bullet evidence later

This file is the single source of truth for "what has been done and why." Git history tracks code changes; this file tracks project-level progress and rationale.
