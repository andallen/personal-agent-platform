#!/usr/bin/env python3
"""
Question Progression Analysis

For the "General Questions 4" conversation (140 user messages, 127 questions),
trace the evolution of questions to detect learning depth changes.

This is the kind of analysis the extraction prompt will need to produce.
Running it deterministically shows what's automatically detectable vs
what needs LLM interpretation.
"""
import json
import re
import zipfile
from pathlib import Path

EXPORTS_DIR = Path.home() / "ai-exports"

# Load "General Questions 4"
with zipfile.ZipFile(EXPORTS_DIR / 'chatgpt_feb.zip') as z:
    conv_files = sorted([f for f in z.namelist() if 'conversations-' in f and f.endswith('.json')])
    target = None
    for cf in conv_files:
        with z.open(cf) as f:
            convos = json.load(f)
        for c in convos:
            if c.get('title') == 'General Questions 4':
                target = c
                break
        if target:
            break

mapping = target['mapping']

# Build ordered messages by walking the tree
children = {}
root = None
for node_id, node in mapping.items():
    parent = node.get('parent')
    if parent is None:
        root = node_id
    else:
        children.setdefault(parent, []).append(node_id)

messages = []
def walk(node_id):
    node = mapping.get(node_id, {})
    msg = node.get('message')
    if msg:
        role = msg.get('author', {}).get('role', '')
        parts = msg.get('content', {}).get('parts', [])
        text = ' '.join(str(p) for p in parts if isinstance(p, str))
        if text.strip() and role in ('user', 'assistant'):
            messages.append({'role': role, 'text': text.strip()})
    for child in children.get(node_id, []):
        walk(child)

walk(root)
user_msgs = [m for m in messages if m['role'] == 'user']

print(f"Total messages: {len(messages)}")
print(f"User messages: {len(user_msgs)}")

# ── Question type classification ────────────────────────────────────
QUESTION_TYPES = {
    'vocabulary': [r'^what (is|are|does) ', r'^what\'?s ', r'^define ', r'^explain (what|the meaning)'],
    'mechanism': [r'^how (does|do|would|can|could) ', r'^how (is|are) .+ (calculated|computed|determined|measured)'],
    'reasoning': [r'^why (does|is|are|do|would|should|can\'t|doesn\'t|isn\'t) ', r'^but why'],
    'comparison': [r'difference between', r'compared to', r'vs\.?\b', r'or is it', r'which (is|one)'],
    'verification': [r'^(is|are|does|do|can|could|would|should) .+\?', r'correct\?', r'right\?', r'am i right'],
    'application': [r'how (would|should|can|could) (i|we|you) ', r'what if ', r'^can (you|i|we) '],
    'example': [r'give (me )?(an? )?example', r'for example', r'such as', r'like what'],
    'clarification': [r'what do you mean', r'i don\'t (get|understand)', r'still (don\'t|confused)', r'explain (it )?(more )?simply'],
}

COMPILED_QT = {cat: [re.compile(p, re.IGNORECASE) for p in patterns] 
               for cat, patterns in QUESTION_TYPES.items()}

def classify_question(text):
    """Classify a question by type."""
    types = []
    for cat, patterns in COMPILED_QT.items():
        for p in patterns:
            if p.search(text):
                types.append(cat)
                break
    return types if types else ['unclassified']


# ── Trace question progression ──────────────────────────────────────
print("\n" + "=" * 70)
print("QUESTION PROGRESSION (first 50 user messages)")
print("=" * 70)

topic_shifts = 0
prev_topic_words = set()
depth_scores = []

for i, m in enumerate(user_msgs[:50]):
    text = m['text']
    q_types = classify_question(text)
    
    # Extract topic words (nouns/verbs that aren't stop words)
    words = set(re.findall(r'\b[a-z]{4,}\b', text.lower()))
    stop = {'what', 'this', 'that', 'with', 'from', 'have', 'does', 'like',
            'just', 'more', 'also', 'very', 'than', 'then', 'even', 'some',
            'would', 'could', 'should', 'about', 'which', 'when', 'where',
            'they', 'their', 'them', 'your', 'into', 'been', 'will', 'each',
            'make', 'much', 'still', 'explain', 'mean', 'does', 'between'}
    topic_words = words - stop
    
    overlap = len(topic_words & prev_topic_words) / max(len(topic_words | prev_topic_words), 1)
    if overlap < 0.15 and i > 0:
        topic_shifts += 1
        shift_marker = " ← TOPIC SHIFT"
    else:
        shift_marker = ""
    
    # Depth heuristic
    depth = 1
    if 'reasoning' in q_types or 'mechanism' in q_types:
        depth = 3
    elif 'comparison' in q_types or 'application' in q_types:
        depth = 4
    elif 'clarification' in q_types:
        depth = 2
    elif 'verification' in q_types:
        depth = 3
    elif 'vocabulary' in q_types:
        depth = 1
    depth_scores.append(depth)
    
    prev_topic_words = topic_words
    
    q_label = '/'.join(q_types)
    print(f"  [{i+1:3d}] [{q_label:<20}] d={depth} {text[:90]}{shift_marker}")

# ── Question type distribution ──────────────────────────────────────
print(f"\n\n{'='*70}")
print("QUESTION TYPE DISTRIBUTION (all {0} user messages)".format(len(user_msgs)))
print(f"{'='*70}")

all_types = []
for m in user_msgs:
    types = classify_question(m['text'])
    all_types.extend(types)

from collections import Counter
type_counts = Counter(all_types)
for qt, count in type_counts.most_common():
    print(f"  {qt:<20} {count:>4} ({count/len(user_msgs)*100:.0f}%)")

# ── Depth progression ───────────────────────────────────────────────
print(f"\n\n{'='*70}")
print("LEARNING DEPTH PROGRESSION")
print(f"{'='*70}")

# Sliding window average
window = 10
if len(depth_scores) > window:
    print(f"  Sliding window (size={window}):")
    for i in range(0, len(depth_scores) - window + 1, window):
        chunk = depth_scores[i:i+window]
        avg = sum(chunk) / len(chunk)
        bar = "█" * int(avg * 10)
        print(f"    Msgs {i+1:>3}-{i+window:<3}: depth={avg:.1f} {bar}")

# Overall trajectory
first_quarter = depth_scores[:len(depth_scores)//4]
last_quarter = depth_scores[-len(depth_scores)//4:]
first_avg = sum(first_quarter) / len(first_quarter)
last_avg = sum(last_quarter) / len(last_quarter)

if last_avg > first_avg + 0.5:
    trajectory = "DEEPENING — questions get more sophisticated"
elif last_avg < first_avg - 0.5:
    trajectory = "BROADENING — shifting to new topics"
else:
    trajectory = "STEADY — consistent depth throughout"

print(f"\n  First quarter avg depth: {first_avg:.1f}")
print(f"  Last quarter avg depth: {last_avg:.1f}")
print(f"  Trajectory: {trajectory}")
print(f"  Topic shifts detected: {topic_shifts}")

# ── Domain topic shifts ─────────────────────────────────────────────
print(f"\n\n{'='*70}")
print("DOMAIN TOPIC SHIFTS (major subject changes)")
print(f"{'='*70}")

# Group messages into topic segments
segments = []
current_segment = {'start': 0, 'messages': [user_msgs[0]['text']]}
for i in range(1, len(user_msgs)):
    words = set(re.findall(r'\b[a-z]{4,}\b', user_msgs[i]['text'].lower())) - stop
    prev_words = set(re.findall(r'\b[a-z]{4,}\b', user_msgs[i-1]['text'].lower())) - stop
    overlap = len(words & prev_words) / max(len(words | prev_words), 1)
    
    if overlap < 0.1 and len(current_segment['messages']) >= 2:
        current_segment['end'] = i - 1
        segments.append(current_segment)
        current_segment = {'start': i, 'messages': [user_msgs[i]['text']]}
    else:
        current_segment['messages'].append(user_msgs[i]['text'])

current_segment['end'] = len(user_msgs) - 1
segments.append(current_segment)

print(f"  Detected {len(segments)} topic segments:")
for seg in segments[:15]:
    first_msg = seg['messages'][0][:80]
    n = len(seg['messages'])
    print(f"    Msgs {seg['start']+1}-{seg['end']+1} ({n} msgs): \"{first_msg}\"")
if len(segments) > 15:
    print(f"    ... +{len(segments)-15} more segments")

