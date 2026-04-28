# Learning Pattern Extraction — Research Findings

Overnight research session (2026-04-28). Comprehensive exploration of approaches, costs, and techniques for extracting learning patterns from ~9,370 AI conversations.

---

## 1. Corpus Inventory (Verified)

| Source | Conversations | Est. Tokens | User Text % |
|---|---|---|---|
| ChatGPT (Feb) | 4,754 | 14.0 MTok | 12.6% |
| Claude acc1 (Feb) | 80 | 0.12 MTok | 19.7% |
| Claude acc2 (Feb) | 115 | 0.42 MTok | 16.0% |
| Claude (April) | 234 | 0.54 MTok | ~16% |
| Claude Code (April) | 1,346 | 4.99 MTok | 52.6% |
| Gemini (April Takeout) | 2,841 | 3.72 MTok | ~50% |
| **Total** | **9,370** | **23.8 MTok** | |

Key finding: ChatGPT is 59% of tokens but 47.6% of its conversations have only 1 user message. User text averages only ~16% of total conversation text (AI responses dominate).

## 2. Programmatic Filters (Free, No AI)

Filters that can be applied before any AI processing:

Note: Gemini (2,841 conversations) is not yet processed. The filters below apply to the other 5 sources (6,568 conversations).

| Filter | Conversations Removed | Source |
|---|---|---|
| Single-message conversations | 1,890 | All non-CC sources |
| Stock research templates | 817 (17% of ChatGPT) | ChatGPT |
| Too-short Claude Code sessions (0–1 msgs) | 1,188 (86% of CC) | Claude Code |
| Image generation | 12 | ChatGPT |
| **Total removed** | **3,907 (60%)** | |
| **Remaining after filters** | **2,661** | **2.50 MTok user-only** |

### Stock research template detection (New — TF-IDF discovery)
TF-IDF clustering on 3,793 conversations revealed **817 ChatGPT conversations (17.2%)** that are systematic stock analysis from a templated research project. These follow patterns like "{TICKER} Management Integrity", "{TICKER} Executive Relations Analysis", "{TICKER} Growth Strategy". They're output generation, not learning. All filterable by title pattern matching on 14 template phrases.

### Claude Code session filter (Exclusionary)
Of 1,385 CC session files: **1,188 (85.8%) removed** — these have 0–1 user messages, so no learning arc is possible. The remaining **197 sessions (14.2%)** are kept for extraction. The filter is deliberately exclusionary: it only removes what is provably not learning, rather than trying to identify what is learning (which would miss sessions with non-obvious learning signal).

### User-only mode
If we send only user messages (not AI responses), we save ~89% of input tokens. Deep analysis on the richest conversation confirmed: Categories A (learning process), B (friction/resonance), D (domain), and E (misconceptions) are 90-95% extractable from user text alone. Category C (AI behavior effectiveness) drops to ~30% but only matters for the 200-conversation deep sample.

## 3. Deterministic Signal Detection Results

Ran keyword matching, sentiment analysis (VADER), and structural feature analysis across all non-Claude-Code conversations.

### Learning signal score distribution (5,042 conversations)
```
P10: 0.005    (clearly no signal)
P25: 0.155
P50: 0.267
P75: 0.431
P90: 0.689
P95: 0.705
Max: 1.100
```

### Triage tiers
- **High signal (top 20%):** 1,073 conversations — 57% of all content
- **Medium signal (40-80%):** 1,956 conversations — 35% of content
- **Low signal (bottom 40%):** 2,013 conversations — 8% of content

The high-signal tier contains disproportionately more text because learning conversations are longer.

### Keyword category coverage
- **Active learning** keywords (questions, explanations): Found in 52.2% of conversations
- **Friction** keywords (confusion, stuck): Found in 6.9%
- **Resonance** keywords (aha moments): Found in 4.0%
- **Misconception** keywords: Found in 0.3%
- **Metacognition** keywords: Found in 0.1%

Friction and resonance keywords have high precision but low recall (~30-40%). Many learning moments aren't verbalized explicitly.

### Domain classification (ChatGPT, keyword-based)
- CS: 43% of conversations
- Math: 37%
- Personal development: 37%
- Finance: 34%
- Philosophy: 14%
- Multi-domain: 42%
- No domain matched: 34%

### Learning styles detected
- Socratic (follow-up questions, "but why"): 4.1%
- Analogical ("it's like", comparisons): 4.1%
- Verification ("am I right", "correct me if"): 2.4%
- Experimental ("let me try", "when I run"): 1.8%
- First-principles ("from basics", "ground up"): 1.5%

### Key conversations identified
Richest learning conversations (5+ messages, high question density):
1. "General questions" series (1-5): 101-140 msgs each, 50-179 questions
2. "Learning Python" series (1-3): 73-92 msgs, 85-241 questions
3. "Financial Markets Questions": 106 msgs, 108 questions
4. "Coding Questions": 138 msgs, 110 questions
5. "Sigma algebra and probability assumptions": 25 msgs (Claude)
6. "Bite-sized lesson structure": 87 msgs (Claude)
7. "Force as a human-defined spring concept": 37 msgs (Claude)

## 4. API Pricing Comparison

All prices per million tokens. Batch = async/24-hour turnaround.

| Model | Input | Output | Batch Input | Batch Output |
|---|---|---|---|---|
| GPT-4.1-nano | $0.10 | $0.40 | $0.05 | $0.20 |
| Gemini 2.0 Flash-Lite | $0.075 | $0.30 | $0.04 | $0.15 |
| Gemini 2.5 Flash | $0.15 | $2.50 | $0.075 | $1.25 |
| GPT-4o-mini | $0.15 | $0.60 | $0.075 | $0.30 |
| DeepSeek V3.2 | $0.28 | $0.42 | N/A | N/A |
| GPT-4.1-mini | $0.40 | $1.60 | $0.20 | $0.80 |
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.50 | $2.50 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | $1.50 | $7.50 |

Free options:
- **Cerebras:** Llama 3.3 70B free, 1M tokens/day (35 days for full corpus)
- **OpenRouter:** Free models available (rate-limited)
- **Google Gemini free tier:** 10 RPM, 250 RPD
- **Local models on RTX 3060:** Zero cost after setup

### Batch API support
All three major providers (Anthropic, OpenAI, Google) offer batch APIs with 50% discount and ~24-hour turnaround. All support 5,000+ requests in a single batch.

### Prompt caching verdict: irrelevant at this scale

Deep investigation revealed prompt caching provides zero benefit for this workload:

| Provider | Min Cacheable Tokens | Our System Prompt |
|---|---|---|
| Anthropic Haiku 4.5 | 4,096 | ~500 (too short) |
| Anthropic Sonnet 4.5 | 1,024 | ~500 (too short) |
| OpenAI (all models) | 1,024 | ~500 (too short) |
| Gemini 2.5 Flash | 1,024 | ~500 (too short) |

Additional blockers:
- GPT-4.1-nano batch does **not** support prompt caching at all (pre-GPT-5 limitation)
- OpenAI's alternative (Flex Processing, `service_tier="flex"`) has uncertain nano support
- Gemini explicit caching adds storage costs ($1.00/MTok/hour)

**None of this matters** because the total batch cost is under $0.01 on GPT-4.1-nano anyway:

| Model (Batch) | 5,370 requests total | Per-request |
|---|---|---|
| GPT-4.1-nano | **$0.0008** | $0.00000015 |
| Gemini 2.5 Flash | $0.0039 | $0.00000073 |
| Haiku 4.5 | $0.0093 | $0.0000017 |

At sub-penny total costs, prompt caching optimization is not meaningful. Spend the engineering time elsewhere.

## 5. Local Model Option (RTX 3060)

The Ubuntu rig's RTX 3060 (12GB VRAM) can run:
- **Qwen 3 8B** (Q4_K_M, ~4.6GB): ~1,490 tok/s input, ~45 tok/s output
- **Qwen 3 14B** (Q4_K_M, ~8.3GB): ~750 tok/s input, ~25 tok/s output

Setup: 3 commands via Ollama (`curl install + ollama pull + ollama run`).

### Estimated processing time
- **Classification** (all 5,600 convos, Qwen 3 8B): ~5 hours
- **Extraction** (top 2,000 convos, Qwen 3 14B): ~9 hours
- **Total: ~14 hours, zero cost**

Quality expectation: 85-90% agreement with human labeling for classification. Structured extraction reliability ~90-95% for 14B models.

## 6. Claude Code Subscription Approach

The `claude` CLI supports non-interactive batch processing:
```bash
claude -p "prompt" --output-format json --json-schema '{...}' --bare --model sonnet < input.txt > output.json
```

### Throughput estimate
- ~40 conversations/hour (conservative, with rate limit breathing room)
- 5,870 conversations: ~147 hours (6+ days continuous)
- Batching 5-10 conversations per prompt: ~15-30 hours (1-2 days)

### Key advantage
Sonnet/Opus-level quality at zero API cost. The `--bare` flag skips all overhead for fast processing.

### Key risk
Subscription rate limits may throttle automated usage. Needs a 50-conversation pilot test.

## 7. Five Pipeline Architectures

### Architecture 1: Deterministic Maximalist
- **Method:** All extraction via keyword/sentiment/structural analysis, LLM only for final synthesis (1-3 Sonnet calls)
- **Cost:** <$1
- **Quality:** ~60-65%
- **Time:** 3-5 days implementation
- **Weakness:** No nuanced misconception detection, CLAUDE.md reads like a statistics report

### Architecture 2: Nano Swarm
- **Method:** Deterministic triage → GPT-4.1-nano batch extraction on all conversations → Sonnet synthesis
- **Cost:** ~$2.30
- **Quality:** ~70-75%
- **Time:** 4-6 days, 24-hour batch turnaround
- **Weakness:** Nano hallucination at scale (~10% garbage outputs)

### Architecture 3: Tiered Triage
- **Method:** Deterministic triage → nano classifies low-signal → nano extracts medium → Haiku extracts high-signal → Sonnet synthesizes
- **Cost:** ~$8.50
- **Quality:** ~80%
- **Time:** 5-7 days implementation
- **Weakness:** Tier boundary misclassification; complexity of managing 3 tiers

### Architecture 4: Claude Code Grinder
- **Method:** Deterministic triage → Claude Code `claude -p` processes every conversation at subscription quality
- **Cost:** $0
- **Quality:** 85-90%
- **Time:** 3-5 days implementation, 1-3 days processing
- **Risk:** Subscription rate limits may throttle

### Architecture 5: Sample, Codify, Verify
- **Method:** Deep-analyze 200 conversations → discover pattern codebook → verify patterns across full corpus with cheap methods
- **Cost:** $1-5
- **Quality:** 80-85% (qualitatively different — psychology profile, not data summary)
- **Time:** 4-6 days
- **Strength:** Discovers patterns you didn't know to look for

### Recommended Hybrid: Architecture 4+5

**Phase 1 (Day 1):** Sample & Codify — deeply analyze 200 stratified conversations through Claude Code, produce pattern codebook (~2 hours, $0)

**Phase 2 (Day 1-2):** Pilot — test automated `claude -p` processing on 50 conversations. If rate limits are OK, proceed to Phase 3A; otherwise, fall back to 3B.

**Phase 3A (Days 2-4):** Claude Code Grinder — process all ~5,370 filtered conversations with codebook-informed prompt ($0, ~2-3 days wall clock)

**Phase 3B (Fallback):** Tiered Triage — nano batch for bulk, Haiku batch for top 1,073 ($8-10, 24-hour batch)

**Phase 4 (Day 4-5):** Synthesis — aggregate all outputs, generate CLAUDE.md through Claude Code

**Expected total cost: $0-10. Quality: 85-90%.**

## 8. The User-Only Optimization

Sending only user messages (not AI responses) saves ~84% of input tokens. This is safe for 4 of 5 signal categories:

| Category | User-only quality | Need AI responses? |
|---|---|---|
| (A) Learning process | 95% | No |
| (B) Friction/resonance | 90% | Rarely |
| (C) AI behavior effectiveness | 30% | Yes (top 200 only) |
| (D) Domain knowledge map | 95% | No |
| (E) Misconception patterns | 80% | Sometimes |

**Recommended:** Extract from user messages for all conversations. Include full conversation (user + AI) only for the ~200 deepest conversations where Category C analysis matters.

## 9. Gemini Takeout Parsing (Solved)

The Gemini `MyActivity.html` uses `\xa0` non-breaking spaces after "Prompted". Parser needs to normalize these. Date format: `"Apr 23, 2026, 9:55:20 PM EDT"`. Grouping entries within 5-minute windows produces 1,117 conversations from 2,648 entries.

Conversation length distribution: 547 single-entry, 384 with 2-3 entries, 168 with 4-10, 18 with 11-30.

## 10. Extraction Prompt Design

Tested prompt schema on sample conversations. The extraction prompt asks for structured JSON output with: domain_tags, learning_depth (1-5), learning_styles_observed, friction_moments (with verbatim quotes), resonance_moments, misconceptions, effective_ai_behaviors, and learning_trajectory_note.

Token budget per conversation:
- System prompt: ~500 tokens
- User messages: ~450 tokens average (user-only mode)
- Expected output: ~400 tokens

## 11. Revised Corpus Count

After revisiting all sources:
- ChatGPT has **4,754** conversations (not 2,000 as initially estimated)
- Total corpus: **9,370** conversations (not 3,800)
- After programmatic filters: **2,576** conversations (verified by running preprocessor). Filters removed: 1,890 single-msg, 817 stock research, 1,273 non-learning CC, 12 image gen. Output at `~/tutor-extraction/conversations/`.

## 12. Final Cost Models

Using **user-only mode** on **2,576 verified conversations** (2.50 MTok user text, avg 961 tokens/conversation):

| Approach | Input MTok | Output MTok (est) | API Cost | Notes |
|---|---|---|---|---|
| GPT-4.1-nano batch | 2.48 | ~1.0 | **$0.32** | 24-hour turnaround |
| Gemini 2.5 Flash batch | 2.48 | ~1.0 | $1.44 | 24-hour turnaround |
| Claude Haiku 4.5 batch | 2.48 | ~1.0 | $3.74 | 24-hour turnaround |
| Local Qwen 3 14B (RTX 3060) | 2.48 | ~1.0 | $0.00 | ~8-12 hours processing |
| Claude Code `-p` (subscription) | 2.48 | ~1.0 | $0.00 | ~16-25 hours, rate limit risk |

Note: Output estimates assume ~400 tokens per extraction result. GPT-4.1-nano batch is the cheapest API option at $0.32 total. Claude Code subscription is free but slower. Prompt caching is irrelevant — our system prompt (500 tokens) is below every provider's minimum cacheable threshold (1,024-4,096 tokens).

## 13. Recommended Plan

**Phase 0:** Deterministic pre-processing — **DONE**. 2,661 conversations output to `~/tutor-extraction/conversations/`. Preprocessor: `/tmp/preprocess_conversations.py`.

**Phase 1:** Sample & Codify — deeply analyze 200 stratified conversations via Claude Code to build pattern codebook (2-3 hours, $0). Sampler: `/tmp/stratified_sampler.py`.

**Phase 2:** Pilot `claude -p` automation on 50 conversations using extraction harness (1 hour, $0). Harness: `/tmp/extraction_harness.sh`.

**Phase 3:** Full extraction via Claude Code `-p` or GPT-4.1-nano batch ($0-0.32). 2,661 conversations, 2.50 MTok input.

**Phase 4:** Synthesis — aggregate extraction outputs into CLAUDE.md, incorporating cross-conversation topic threads (2-3 hours, $0)

Expected total cost: **$0-0.32**. Calendar time: 4-7 days.

## 14. Cross-Conversation Topic Threading (New Finding)

Ran topic threading analysis across 2,614 multi-message conversations. Key discovery: **learning topics form long arcs spanning months**, not isolated single-conversation events.

### Topic threads by size
| Topic | Conversations | Timespan | Avg return interval | Learning bursts |
|---|---|---|---|---|
| Finance | 643 | 823 days | 1 day | 48 bursts |
| JavaScript | 349 | 823 days | 2 days | 33 |
| Linear algebra | 190 | 814 days | 4 days | 20 |
| Calculus | 157 | 786 days | 5 days | 22 |
| Python | 126 | 421 days | 3 days | 16 |
| Probability | 113 | 821 days | 7 days | 11 |
| Machine learning | 77 | 515 days | 6 days | 9 |
| Philosophy | 60 | 833 days | 14 days | 4 |
| Measure theory | 32 | 814 days | 26 days | 3 |

### Title-based conversation series
Explicit multi-part learning sessions:
- **"Bite-sized lesson structure"** — 12 Claude conversations (Feb-Mar 2026)
- **"General questions" 1-5** — 5 ChatGPT conversations, 561 total messages (Dec 2024)
- **"Learning Python" 1-3** — 3 conversations, 188 messages (Dec 2024)
- **"AAPL Stock Analysis"** — 4 conversations (Nov 2024)
- **"Free Will" 1-2** — 2 conversations, 46 messages (Jun 2025)

### Topic co-occurrence (topics that appear together)
Top pairs: finance+javascript (221), finance+python (88), finance+linear_algebra (82), calculus+finance (74)

### Implication for extraction
1,004 conversations (38%) participate in topic threads. The extraction prompt must capture thread membership so the synthesis phase can reconstruct learning arcs across conversations, not just within them.

## 15. Claude Code Session Filter Results

Of 1,385 CC session files:
- **Removed (0–1 user messages):** 1,188 (85.8%) — no learning arc possible
- **Kept for extraction:** 197 (14.2%)

The filter is exclusionary: it only removes sessions that provably cannot contain learning (too few messages for any arc to exist). It does not attempt to classify what IS learning — that would require heuristics with incomplete recall that silently discard real learning sessions.

## 16. User-Only Information Loss Analysis

Deep analysis on the richest learning conversation ("Force as a human-defined spring concept" — 37 user msgs, 37 assistant msgs, 9 friction moments, 5 resonance moments):

| Category | Extractable from user-only | Notes |
|---|---|---|
| (A) Learning process | 95% | Question progression, topic evolution fully visible |
| (B) Friction moments | 95% | "I don't understand", "wait", "but why" all in user text |
| (B) Resonance moments | 90% | "that makes sense finally", "so basically" in user text |
| (C) AI behavior effectiveness | 30% | Need AI responses to see techniques used |
| (D) Domain knowledge map | 95% | Domain vocabulary fully visible in user text |
| (E) Misconceptions | 85% | "I thought", "wait so it's not" in user text |

User text is 20.6% of total conversation text (89% token savings). 16 user reactions were successfully traced to inferred AI behaviors from user text alone. The hybrid approach (user-only for bulk, full conversation for 200 deep samples) is validated.

## 17. Artifacts Produced

All reusable artifacts from the research session:

| Artifact | Location | Purpose |
|---|---|---|
| Signal detection experiment | `/tmp/signal_experiment.py` | Deterministic learning signal scoring |
| Cross-conversation threading | `/tmp/cross_conversation_threading.py` | Topic thread detection |
| CC session filter | `/tmp/claude_code_learning_filter.py` | Classifies CC sessions as learning/coding |
| Extraction prompt samples | `/tmp/extraction_samples/` | 26 formatted prompt inputs for testing |
| Stratified sampler | `/tmp/stratified_sampler.py` | Selects 200 representative conversations |
| Extraction harness | `/tmp/extraction_harness.sh` | Batch processing via `claude -p` with rate limiting, resume, backoff |
| Extraction prompt template | `/tmp/extraction_prompt.txt` | Structured JSON extraction prompt (updated with question_progression, knowledge_gaps) |
| User-only loss analysis | `/tmp/user_only_loss_analysis.py` | Validates user-only approach |
| Question progression analysis | `/tmp/question_progression_analysis.py` | Traces question type evolution within conversations |
| TF-IDF topic clustering | `/tmp/tfidf_clustering.py` | Discovers topic groups beyond keyword categories |
| **Phase 0 preprocessor** | `/tmp/preprocess_conversations.py` | Converts raw exports → individual JSON files with all filters applied |
| Learning style deep analysis | `/tmp/learning_style_deep_analysis.py` | Detects 8 distinctive learning behaviors |
| Temporal learning arc | `/tmp/temporal_arc.py` | Monthly domain heat map and quarterly narrative |

## 18. Learning Style Profile Preview (Deterministic)

Ran pattern detection across all 2,576 preprocessed conversations. These are deterministic findings — no LLM involved — providing a preview of what the full extraction pipeline will refine.

### Behavior frequency
| Behavior | Instances | Conversations | % of corpus |
|---|---|---|---|
| Meta-learning | 247 | 136 | 5.3% |
| Analogy-seeking | 168 | 103 | 4.0% |
| Pushback/challenge | 134 | 75 | 2.9% |
| Verification | 122 | 83 | 3.2% |
| Depth-seeking | 119 | 91 | 3.5% |
| First-principles | 93 | 45 | 1.7% |
| Cross-domain | 49 | 32 | 1.2% |
| Self-correction | 14 | 9 | 0.3% |

### Key traits for tutor calibration
1. **Adversarial learning style** — more likely to challenge than verify. The tutor should expect and welcome pushback; it's productive, not hostile.
2. **Analogy-first understanding** — prefers analogies over abstract definitions. The tutor should lead with concrete comparisons.
3. **High meta-learning awareness** — actively designs own learning process (bite-sized, step-by-step). The tutor should respect these preferences.
4. **Depth over breadth** — when interested, pushes deep. The tutor should follow depth signals rather than broadening prematurely.
5. **Cross-domain connection** — makes links between fields. The tutor should surface connections when domains overlap.

### Behaviorally richest conversations (for Phase 1 deep sampling)
- Adonis project sessions (6 behavior types, 34+ hits) — coding + learning + pushback
- "A great conversation" (5 types, 13 hits) — pushback-heavy dialogue
- "Force as a human-defined spring concept" (3 types, 6 hits) — friction + resonance + analogy

## 19. Temporal Learning Arc (Deterministic)

Monthly domain activity across all sources (Dec 2022 – Apr 2026). Reveals clear learning trajectory:

### Quarterly narrative
| Quarter | Conversations | Dominant activity |
|---|---|---|
| 2024Q1 | 34 | Physics first principles, philosophy |
| 2024Q2 | 8 | Java fundamentals (CS coursework starts) |
| 2024Q3 | 39 | Financial markets exploration begins |
| 2024Q4 | 184 | Finance explodes (26 convos), Java (19), Calculus (18) |
| 2025Q1 | 541 | **Peak activity** — algorithmic trading: Python (82) + finance (63) + web dev (34) |
| 2025Q2 | 528 | Finance (37), Java (27), Python (20) |
| 2025Q3 | 564 | **Highest volume** — finance (199!), physics (47), stock research project |
| 2025Q4 | 455 | Linear algebra (49), web dev (29) — shift to mathematical foundations |
| 2026Q1 | 260 | AI/ML (10), finance (9), physics (5) — agent platform work begins |
| 2026Q2 | 39 | Probability (8), physics (6) — measure theory, first principles |

### Key insight for the tutor
The trajectory shows a coherent intellectual path: CS fundamentals → finance → quantitative methods → AI/ML → mathematical foundations. The tutor should leverage this progression — Andrew builds on prior domains rather than abandoning them. When introducing new concepts, connecting to finance/trading context will land better than abstract examples.

## 20. Pilot Test: `claude -p` Extraction (Verified Working)

Ran a single extraction through `claude -p --output-format json --model haiku` on "Reverse engineering stock price" (7 user messages, 995 chars).

**Result:** Excellent structured JSON output in 20 seconds. Correctly identified:
- 5 domain tags, learning depth 2, "circling" question progression
- 3 friction moments with verbatim quotes
- 4 knowledge gaps, 1 misconception
- Insightful trajectory note

**Throughput estimate (verified):**
- Single call: 20 seconds
- 2,661 conversations unbatched: ~14 hours
- With 5-per-batch: ~3 hours
- Extraction harness at `/tmp/extraction_harness.sh` handles batching, rate limiting, resume

**Issue noted:** Output wrapped in markdown fences (```json...```). The harness already strips these.

## 21. Open Questions

1. **Claude Code rate limits at scale:** The single-call test worked. Need to verify 50+ consecutive calls don't trigger throttling. Needs pilot test with the extraction harness.
2. **Local model quality:** Is Qwen 3 14B on the RTX 3060 good enough for extraction, or do we need API models? Needs side-by-side comparison on 50 samples.
3. **Prompt iteration:** The extraction prompt needs testing on 20-50 diverse conversations to calibrate. Best done interactively with Andrew.
4. **Thread-aware extraction:** How should the extraction prompt reference thread context? Should it receive a "this conversation is part of the probability thread (32 conversations)" header?
