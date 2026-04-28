#!/usr/bin/env python3
"""
Deterministic Learning Signal Detection Experiment

Tests keyword/regex, sentiment analysis, and structural features
on real conversation data from ~/ai-exports/ to measure how much
learning signal we can detect without any LLM API calls.
"""

import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

EXPORTS_DIR = Path.home() / "ai-exports"
vader = SentimentIntensityAnalyzer()

# ── Signal keyword dictionaries ──────────────────────────────────────
LEARNING_KEYWORDS = {
    'friction': [
        r"i don'?t understand",
        r"i'?m confused",
        r"doesn'?t make sense",
        r"wait what",
        r"i'?m lost",
        r"huh\??",
        r"that'?s confusing",
        r"can you clarify",
        r"i keep getting",
        r"still not working",
        r"i'?m stuck",
        r"what do you mean",
        r"why (doesn'?t|isn'?t|won'?t|can'?t)",
        r"how (does|do|is) that",
        r"but (why|how|what)",
        r"that can'?t be right",
        r"i thought",
        r"shouldn'?t it be",
    ],
    'resonance': [
        r"oh i see",
        r"that makes sense",
        r"aha",
        r"now i get it",
        r"oh wait",
        r"that clicked",
        r"ohhh",
        r"so basically",
        r"so it'?s (like|basically|essentially)",
        r"interesting",
        r"makes sense now",
        r"got it",
        r"right,? so",
    ],
    'active_learning': [
        r"can you explain",
        r"what (is|are|does|do) ",
        r"how (do|does|would|should|can|could) ",
        r"why (is|are|does|do|would|should) ",
        r"for example",
        r"give me an example",
        r"show me",
        r"walk me through",
        r"step by step",
        r"let me try",
        r"what if ",
        r"so does that mean",
        r"is that because",
        r"what'?s the difference between",
        r"compared to",
        r"in other words",
    ],
    'misconception': [
        r"oh wait,? i thought",
        r"i was wrong about",
        r"so it'?s not",
        r"i assumed",
        r"my mistake",
        r"i had it backwards",
        r"that'?s not what i expected",
        r"i see,? so (it'?s|that'?s) actually",
    ],
    'metacognition': [
        r"i think i understand",
        r"let me (think|see|check)",
        r"so to summarize",
        r"if i understand correctly",
        r"correct me if i'?m wrong",
        r"am i right that",
        r"so what (you'?re|you are) saying is",
        r"to make sure i understand",
    ],
}

# Compile all patterns
COMPILED_PATTERNS = {}
for category, patterns in LEARNING_KEYWORDS.items():
    COMPILED_PATTERNS[category] = [re.compile(p, re.IGNORECASE) for p in patterns]


def extract_user_messages(conversation, source_type):
    """Extract user messages from a conversation, handling different formats."""
    messages = []

    if source_type == 'chatgpt':
        mapping = conversation.get('mapping', {})
        for node_id, node in mapping.items():
            msg = node.get('message')
            if msg and msg.get('author', {}).get('role') == 'user':
                parts = msg.get('content', {}).get('parts', [])
                text = ' '.join(str(p) for p in parts if isinstance(p, str))
                if text.strip():
                    messages.append(text.strip())

    elif source_type == 'claude':
        for m in conversation.get('chat_messages', []):
            if m.get('sender') == 'human':
                text = ''
                if isinstance(m.get('text'), str):
                    text = m['text']
                elif isinstance(m.get('content'), list):
                    text = ' '.join(
                        p.get('text', '') for p in m['content']
                        if isinstance(p, dict) and 'text' in p
                    )
                elif isinstance(m.get('content'), str):
                    text = m['content']
                if text.strip():
                    messages.append(text.strip())

    return messages


def analyze_conversation(messages, title=""):
    """Run all deterministic analyses on a conversation's user messages."""
    if not messages:
        return None

    all_text = ' '.join(messages)

    # ── Keyword signal detection ──
    keyword_hits = {}
    total_hits = 0
    for category, patterns in COMPILED_PATTERNS.items():
        hits = 0
        for pattern in patterns:
            hits += len(pattern.findall(all_text))
        keyword_hits[category] = hits
        total_hits += hits

    # ── Structural features ──
    num_messages = len(messages)
    avg_msg_len = sum(len(m) for m in messages) / num_messages
    msg_lens = [len(m) for m in messages]
    msg_len_variance = (
        sum((l - avg_msg_len) ** 2 for l in msg_lens) / num_messages
    ) ** 0.5 if num_messages > 1 else 0

    question_count = sum(m.count('?') for m in messages)
    question_density = question_count / num_messages

    code_blocks = sum(m.count('```') for m in messages) // 2

    # Consecutive short messages (< 50 chars)
    short_runs = 0
    current_run = 0
    for m in messages:
        if len(m) < 50:
            current_run += 1
            if current_run >= 2:
                short_runs += 1
        else:
            current_run = 0

    # ── Sentiment analysis ──
    sentiments = [vader.polarity_scores(m)['compound'] for m in messages]
    avg_sentiment = sum(sentiments) / len(sentiments)
    sentiment_variance = (
        sum((s - avg_sentiment) ** 2 for s in sentiments) / len(sentiments)
    ) ** 0.5 if len(sentiments) > 1 else 0

    # Sentiment inflection points (negative -> positive or vice versa)
    inflections = 0
    for i in range(1, len(sentiments)):
        if (sentiments[i] > 0.2 and sentiments[i-1] < -0.2) or \
           (sentiments[i] < -0.2 and sentiments[i-1] > 0.2):
            inflections += 1

    # ── Composite learning signal score ──
    score = (
        0.20 * min(total_hits / max(num_messages, 1), 2.0)  # keyword density, capped
        + 0.15 * min(question_density, 2.0)                  # question density, capped
        + 0.15 * sentiment_variance                           # emotional journey
        + 0.10 * min(inflections / max(num_messages, 1) * 10, 1.0)  # sentiment swings
        + 0.15 * min(msg_len_variance / 500, 1.0)            # message length variety
        + 0.10 * min(num_messages / 20, 1.0)                 # conversation depth
        + 0.05 * min(code_blocks / 3, 1.0)                   # code experimentation
        + 0.10 * min(keyword_hits.get('friction', 0) + keyword_hits.get('resonance', 0), 5) / 5  # friction+resonance
    )

    return {
        'title': title,
        'num_messages': num_messages,
        'total_chars': len(all_text),
        'keyword_hits': keyword_hits,
        'total_keyword_hits': total_hits,
        'avg_msg_len': avg_msg_len,
        'msg_len_variance': msg_len_variance,
        'question_density': question_density,
        'code_blocks': code_blocks,
        'short_runs': short_runs,
        'avg_sentiment': avg_sentiment,
        'sentiment_variance': sentiment_variance,
        'inflections': inflections,
        'score': score,
    }


def process_source(source_type, data):
    """Process all conversations from a source."""
    results = []
    for conv in data:
        title = conv.get('title') or conv.get('name') or 'untitled'
        messages = extract_user_messages(conv, source_type)
        analysis = analyze_conversation(messages, title)
        if analysis:
            analysis['source'] = source_type
            results.append(analysis)
    return results


# ── Load and process all sources ─────────────────────────────────────
all_results = []

# ChatGPT
print("Processing ChatGPT...")
with zipfile.ZipFile(EXPORTS_DIR / 'chatgpt_feb.zip') as z:
    conv_files = sorted([f for f in z.namelist() if 'conversations-' in f and f.endswith('.json')])
    for cf in conv_files:
        with z.open(cf) as f:
            convos = json.load(f)
        all_results.extend(process_source('chatgpt', convos))

# Claude sources
for source_name in ['claude_acc1_feb', 'claude_acc2_feb']:
    print(f"Processing {source_name}...")
    with open(EXPORTS_DIR / source_name / 'conversations.json') as f:
        convos = json.load(f)
    all_results.extend(process_source('claude', convos))

# Claude April
print("Processing Claude April...")
with zipfile.ZipFile(EXPORTS_DIR / 'claude_april.zip') as z:
    with z.open('conversations.json') as f:
        convos = json.load(f)
    all_results.extend(process_source('claude', convos))

print(f"\nTotal conversations analyzed: {len(all_results)}")

# ── Analysis ─────────────────────────────────────────────────────────

# Score distribution
scores = [r['score'] for r in all_results]
scores.sort()
print("\n" + "=" * 65)
print("LEARNING SIGNAL SCORE DISTRIBUTION")
print("=" * 65)
for pct in [10, 25, 50, 75, 90, 95, 99]:
    idx = int(len(scores) * pct / 100)
    print(f"  P{pct:>2}: {scores[idx]:.3f}")
print(f"  Max: {scores[-1]:.3f}")
print(f"  Mean: {sum(scores)/len(scores):.3f}")

# Tier the conversations
high = [r for r in all_results if r['score'] >= scores[int(len(scores) * 0.8)]]
medium = [r for r in all_results if scores[int(len(scores) * 0.4)] <= r['score'] < scores[int(len(scores) * 0.8)]]
low = [r for r in all_results if r['score'] < scores[int(len(scores) * 0.4)]]

print(f"\n  High signal (top 20%):    {len(high)} conversations")
print(f"  Medium signal (40-80%):   {len(medium)} conversations")
print(f"  Low signal (bottom 40%):  {len(low)} conversations")

# Show top 30 highest-scored conversations
print("\n" + "=" * 65)
print("TOP 30 HIGHEST-SCORED CONVERSATIONS")
print("=" * 65)
top = sorted(all_results, key=lambda r: r['score'], reverse=True)[:30]
for i, r in enumerate(top, 1):
    print(f"  {i:>2}. [{r['score']:.3f}] [{r['source']:<7}] ({r['num_messages']} msgs) {r['title'][:60]}")

# Show keyword hit distribution
print("\n" + "=" * 65)
print("KEYWORD CATEGORY HIT DISTRIBUTION (across all conversations)")
print("=" * 65)
for cat in LEARNING_KEYWORDS:
    hits = sum(r['keyword_hits'].get(cat, 0) for r in all_results)
    convos_with_hits = sum(1 for r in all_results if r['keyword_hits'].get(cat, 0) > 0)
    print(f"  {cat:<20} {hits:>6} total hits across {convos_with_hits:>5} conversations ({convos_with_hits/len(all_results)*100:.1f}%)")

# Show bottom 10 (should be low-signal, verify)
print("\n" + "=" * 65)
print("BOTTOM 10 LOWEST-SCORED (sanity check: should be low-signal)")
print("=" * 65)
bottom = sorted(all_results, key=lambda r: r['score'])[:10]
for i, r in enumerate(bottom, 1):
    print(f"  {i:>2}. [{r['score']:.3f}] [{r['source']:<7}] ({r['num_messages']} msgs) {r['title'][:60]}")

# Source breakdown
print("\n" + "=" * 65)
print("SCORE BREAKDOWN BY SOURCE")
print("=" * 65)
by_source = defaultdict(list)
for r in all_results:
    by_source[r['source']].append(r['score'])
for source, src_scores in sorted(by_source.items()):
    src_scores.sort()
    n = len(src_scores)
    avg = sum(src_scores) / n
    p50 = src_scores[n // 2]
    p90 = src_scores[int(n * 0.9)]
    print(f"  {source:<10} n={n:<5} avg={avg:.3f}  P50={p50:.3f}  P90={p90:.3f}")

# Token savings estimate
total_tokens = sum(r['total_chars'] / 4 for r in all_results)
high_tokens = sum(r['total_chars'] / 4 for r in high)
medium_tokens = sum(r['total_chars'] / 4 for r in medium)
low_tokens = sum(r['total_chars'] / 4 for r in low)

print("\n" + "=" * 65)
print("ESTIMATED TOKEN SAVINGS FROM TRIAGE")
print("=" * 65)
print(f"  Total tokens: {total_tokens:,.0f} ({total_tokens/1e6:.2f} MTok)")
print(f"  High tier (full LLM):  {high_tokens:,.0f} ({high_tokens/total_tokens*100:.1f}%)")
print(f"  Medium tier (targeted): {medium_tokens:,.0f} ({medium_tokens/total_tokens*100:.1f}%)")
print(f"  Low tier (skip/summary): {low_tokens:,.0f} ({low_tokens/total_tokens*100:.1f}%)")
print(f"\n  If we do full extraction on top 20% only: save {(1 - high_tokens/total_tokens)*100:.0f}% of tokens")
print(f"  If we do full on top 60%, skip bottom 40%: save {low_tokens/total_tokens*100:.0f}% of tokens")

# Conversations with ZERO keyword hits
zero_hits = [r for r in all_results if r['total_keyword_hits'] == 0]
print(f"\n  Conversations with ZERO learning keyword hits: {len(zero_hits)} ({len(zero_hits)/len(all_results)*100:.1f}%)")
