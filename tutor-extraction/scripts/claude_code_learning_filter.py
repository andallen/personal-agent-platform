#!/usr/bin/env python3
"""
Claude Code Session Learning Filter Experiment

Claude Code sessions are different from chat conversations:
- Most are pure coding sessions (write code, fix bugs, deploy)
- Some contain genuine learning (user asks why, explores concepts)
- Need to distinguish without false negatives

Tests multiple heuristic approaches on real CC session data.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CC_DIR = Path.home() / "ai-exports" / "claude_code_april"

# Learning signal indicators in Claude Code context
LEARNING_INDICATORS = {
    'conceptual_questions': [
        r"what (is|are|does) ",
        r"why (does|is|do|would|should|can't|doesn't)",
        r"how (does|do|would|should|can|could) .{5,}",
        r"explain",
        r"what's the difference between",
        r"is that because",
        r"i don't understand",
    ],
    'exploration': [
        r"what if (we|i|instead)",
        r"could (we|i) (also|instead|alternatively)",
        r"is there a (better|different|alternative|other) way",
        r"what would happen if",
        r"what are the (pros|cons|trade-?offs|advantages|disadvantages)",
        r"compared to",
    ],
    'learning_dialogue': [
        r"oh i see",
        r"that makes sense",
        r"so basically",
        r"interesting",
        r"i didn't know",
        r"wait,? (so|that|really)",
        r"thanks,? (that|now i|i) ",
        r"can you (walk|talk) me through",
    ],
}

PURE_CODING_INDICATORS = [
    r"^(fix|add|update|remove|delete|create|refactor|rename|move|implement|build|deploy|push|commit|merge|revert|install|run|test|lint|format|ship) ",
    r"^make (it|this|the) ",
    r"^change (the|this) ",
    r"^set up ",
    r"^configure ",
    r"^write (a|the|this) (test|function|class|component|script|hook|handler|endpoint)",
    r"now (do|fix|add|update|remove|change|make) ",
    r"^ok (do|fix|add|update|remove|change|make) ",
    r"^apply ",
    r"looks good",
    r"^ship it",
    r"^lgtm",
    r"^commit",
    r"^y$",
    r"^yes$",
    r"^no$",
    r"^n$",
]

COMPILED_LEARNING = {}
for cat, patterns in LEARNING_INDICATORS.items():
    COMPILED_LEARNING[cat] = [re.compile(p, re.IGNORECASE) for p in patterns]

COMPILED_CODING = [re.compile(p, re.IGNORECASE) for p in PURE_CODING_INDICATORS]


def extract_cc_user_messages(jsonl_path):
    """Extract human messages from a Claude Code JSONL session file."""
    messages = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                if entry.get('type') != 'user':
                    continue
                if entry.get('isMeta', False):
                    continue

                content = entry.get('message', {}).get('content', '')
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = ' '.join(
                        p.get('text', '') for p in content
                        if isinstance(p, dict) and p.get('type') == 'text'
                    )
                else:
                    continue

                # Skip command/skill invocations
                if text.startswith('<command-name>') or text.startswith('/'):
                    continue
                # Skip very short confirmations
                text = text.strip()
                if text and len(text) > 0:
                    messages.append(text)
    except Exception as e:
        return []
    return messages


def classify_session(messages):
    """Classify a Claude Code session as learning vs pure coding."""
    if len(messages) < 2:
        return 'too_short', {}

    learning_hits = defaultdict(int)
    coding_hits = 0

    for msg in messages:
        for cat, patterns in COMPILED_LEARNING.items():
            for p in patterns:
                if p.search(msg):
                    learning_hits[cat] += 1

        for p in COMPILED_CODING:
            if p.search(msg):
                coding_hits += 1

    total_learning = sum(learning_hits.values())
    question_count = sum(m.count('?') for m in messages)

    # Classification heuristics
    score = 0
    reasons = []

    if total_learning >= 5:
        score += 2
        reasons.append(f'{total_learning} learning hits')
    elif total_learning >= 2:
        score += 1
        reasons.append(f'{total_learning} learning hits')

    if question_count >= 3:
        score += 1
        reasons.append(f'{question_count} questions')

    question_ratio = question_count / len(messages)
    if question_ratio > 0.3:
        score += 1
        reasons.append(f'{question_ratio:.0%} question ratio')

    coding_ratio = coding_hits / len(messages) if messages else 0
    if coding_ratio > 0.5:
        score -= 1
        reasons.append(f'{coding_ratio:.0%} coding commands')

    # Average message length — learning messages tend to be longer
    avg_len = sum(len(m) for m in messages) / len(messages)
    if avg_len > 200:
        score += 1
        reasons.append(f'avg msg len {avg_len:.0f}')

    if score >= 2:
        return 'learning', {'score': score, 'reasons': reasons, 'learning_hits': dict(learning_hits), 'coding_hits': coding_hits, 'questions': question_count}
    elif score >= 1:
        return 'maybe_learning', {'score': score, 'reasons': reasons, 'learning_hits': dict(learning_hits), 'coding_hits': coding_hits, 'questions': question_count}
    else:
        return 'pure_coding', {'score': score, 'reasons': reasons, 'learning_hits': dict(learning_hits), 'coding_hits': coding_hits, 'questions': question_count}


# ── Process all Claude Code sessions ────────────────────────────────
sessions = list(CC_DIR.rglob('*.jsonl'))
print(f"Found {len(sessions)} Claude Code session files")

results = []
for session_path in sessions:
    messages = extract_cc_user_messages(session_path)
    classification, details = classify_session(messages)
    results.append({
        'file': session_path.name,
        'num_messages': len(messages),
        'classification': classification,
        'details': details,
        'first_msg': messages[0][:100] if messages else '',
        'messages': messages,
    })

# ── Statistics ──────────────────────────────────────────────────────
class_counts = Counter(r['classification'] for r in results)
print(f"\n{'='*65}")
print("CLASSIFICATION RESULTS")
print(f"{'='*65}")
for cls, count in class_counts.most_common():
    pct = count / len(results) * 100
    print(f"  {cls:<20} {count:>5} ({pct:.1f}%)")

# Show message count distribution by class
print(f"\n{'='*65}")
print("MESSAGE COUNT BY CLASSIFICATION")
print(f"{'='*65}")
for cls in ['learning', 'maybe_learning', 'pure_coding', 'too_short']:
    msgs = [r['num_messages'] for r in results if r['classification'] == cls]
    if msgs:
        avg = sum(msgs) / len(msgs)
        total = sum(msgs)
        print(f"  {cls:<20} avg={avg:.0f} msgs, total={total} msgs, median={sorted(msgs)[len(msgs)//2]}")

# Show top learning sessions
learning = [r for r in results if r['classification'] == 'learning']
learning.sort(key=lambda r: r['details'].get('score', 0), reverse=True)
print(f"\n{'='*65}")
print(f"TOP 20 LEARNING SESSIONS (of {len(learning)})")
print(f"{'='*65}")
for r in learning[:20]:
    d = r['details']
    print(f"  [{d['score']}] {r['file'][:40]} ({r['num_messages']} msgs, {d['questions']}q) {', '.join(d['reasons'][:3])}")
    # Show a sample learning message
    for msg in r['messages']:
        for cat, patterns in COMPILED_LEARNING.items():
            for p in patterns:
                if p.search(msg):
                    print(f"      → \"{msg[:100]}\"")
                    break
            else:
                continue
            break

# Show maybe_learning sessions (borderline — valuable for calibration)
maybe = [r for r in results if r['classification'] == 'maybe_learning']
print(f"\n{'='*65}")
print(f"MAYBE-LEARNING SESSIONS ({len(maybe)} — need manual review)")
print(f"{'='*65}")
for r in maybe[:15]:
    d = r['details']
    print(f"  [{d['score']}] {r['file'][:40]} ({r['num_messages']} msgs, {d['questions']}q) {', '.join(d['reasons'][:3])}")
    print(f"      first msg: \"{r['first_msg'][:80]}\"")

# Estimate token savings
total_tokens_all = sum(sum(len(m) for m in r['messages']) / 4 for r in results)
total_tokens_learning = sum(sum(len(m) for m in r['messages']) / 4 for r in results if r['classification'] in ('learning', 'maybe_learning'))
total_tokens_coding = sum(sum(len(m) for m in r['messages']) / 4 for r in results if r['classification'] == 'pure_coding')

print(f"\n{'='*65}")
print("TOKEN SAVINGS FROM CLAUDE CODE FILTERING")
print(f"{'='*65}")
print(f"  Total CC user tokens: {total_tokens_all:,.0f} ({total_tokens_all/1e6:.2f} MTok)")
print(f"  Learning/maybe tokens: {total_tokens_learning:,.0f} ({total_tokens_learning/total_tokens_all*100:.1f}%)")
print(f"  Pure coding tokens: {total_tokens_coding:,.0f} ({total_tokens_coding/total_tokens_all*100:.1f}%)")
print(f"  Filtering saves: {total_tokens_coding/total_tokens_all*100:.0f}% of CC tokens")

