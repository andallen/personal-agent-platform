#!/usr/bin/env python3
"""
Phase 0: Preprocess Raw Exports → Individual Conversation Files

Takes raw AI conversation exports from ~/ai-exports/ and produces
individual JSON files ready for the extraction harness.

Each output file: {id, source, title, user_messages, metadata}

Applies all programmatic filters:
1. Drop 1-message conversations
2. Drop stock research template conversations (ChatGPT)
3. Drop image generation conversations (ChatGPT)
4. Drop non-learning Claude Code sessions (91%)
5. (Gemini parsing handled separately)
"""
import json
import hashlib
import re
import zipfile
from collections import Counter
from pathlib import Path

EXPORTS_DIR = Path.home() / "ai-exports"
OUTPUT_DIR = Path.home() / "tutor-extraction" / "conversations"

STOCK_PATTERNS = [
    'Management Integrity', 'Executive Relations', 'Sales Organization',
    'Market Potential', 'Growth Strategy', 'Profit Margin', 'Profit Outlook',
    'Labor Relations', 'Equity Financing', 'Management Transparency',
    'Management Succession', 'Management Depth', 'Growth Potential',
    'Operating Margin',
]


def make_id(source, title, index):
    """Generate a deterministic ID for a conversation."""
    raw = f"{source}:{title}:{index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def is_stock_research(title):
    """Check if a ChatGPT conversation is from the stock research template."""
    if not title:
        return False
    return any(p.lower() in title.lower() for p in STOCK_PATTERNS)


def is_image_generation(title):
    if not title:
        return False
    return 'image' in title.lower() and ('generat' in title.lower() or 'request' in title.lower())


def extract_chatgpt_user_messages(conv):
    mapping = conv.get('mapping', {})
    messages = []
    for node in mapping.values():
        msg = node.get('message')
        if msg is None:
            continue
        author = msg.get('author')
        if author is None:
            continue
        if author.get('role') != 'user':
            continue
        parts = msg.get('content', {}).get('parts', [])
        text = ' '.join(str(p) for p in parts if isinstance(p, str))
        if text.strip():
            messages.append(text.strip())
    return messages


def extract_claude_user_messages(conv):
    messages = []
    for m in conv.get('chat_messages', []):
        if m.get('sender') != 'human':
            continue
        text = ''
        if isinstance(m.get('text'), str):
            text = m['text']
        elif isinstance(m.get('content'), list):
            text = ' '.join(p.get('text', '') for p in m['content']
                           if isinstance(p, dict) and 'text' in p)
        elif isinstance(m.get('content'), str):
            text = m['content']
        if text.strip():
            messages.append(text.strip())
    return messages


def extract_cc_user_messages(jsonl_path):
    messages = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if entry.get('type') != 'user' or entry.get('isMeta', False):
                    continue
                content = entry.get('message', {}).get('content', '')
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = ' '.join(p.get('text', '') for p in content
                                   if isinstance(p, dict) and p.get('type') == 'text')
                else:
                    continue
                if text.startswith('<command-name>') or text.startswith('/'):
                    continue
                if text.startswith('<local-command-stdout>'):
                    continue
                text = text.strip()
                if text:
                    messages.append(text)
    except Exception:
        return []
    return messages


def is_cc_definitely_not_learning(messages):
    """Returns True only if we can PROVE this session has no learning.
    Only condition: 0-1 user messages (no arc possible)."""
    return len(messages) < 2


def write_conversation(conv_id, source, title, messages, output_dir):
    """Write a preprocessed conversation to disk."""
    output = {
        'id': conv_id,
        'source': source,
        'title': title,
        'user_messages': messages,
        'metadata': {
            'num_messages': len(messages),
            'total_chars': sum(len(m) for m in messages),
        }
    }
    path = output_dir / f"{conv_id}.json"
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)
    return path


# ── Main processing ─────────────────────────────────────────────────
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

stats = Counter()
idx = Counter()

# ChatGPT
print("Processing ChatGPT...")
with zipfile.ZipFile(EXPORTS_DIR / 'chatgpt_feb.zip') as z:
    conv_files = sorted([f for f in z.namelist() if 'conversations-' in f and f.endswith('.json')])
    for cf in conv_files:
        with z.open(cf) as f:
            convos = json.load(f)
        for c in convos:
            stats['chatgpt_total'] += 1
            title = c.get('title') or 'untitled'
            
            if is_stock_research(title):
                stats['filtered_stock'] += 1
                continue
            if is_image_generation(title):
                stats['filtered_image'] += 1
                continue
            
            messages = extract_chatgpt_user_messages(c)
            if len(messages) <= 1:
                stats['filtered_single_msg'] += 1
                continue
            
            idx['chatgpt'] += 1
            conv_id = make_id('chatgpt', title, idx['chatgpt'])
            write_conversation(conv_id, 'chatgpt', title, messages, OUTPUT_DIR)
            stats['chatgpt_kept'] += 1

# Claude
for source_name in ['claude_acc1_feb', 'claude_acc2_feb']:
    print(f"Processing {source_name}...")
    with open(EXPORTS_DIR / source_name / 'conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        stats[f'{source_name}_total'] += 1
        title = c.get('name') or 'untitled'
        messages = extract_claude_user_messages(c)
        if len(messages) <= 1:
            stats['filtered_single_msg'] += 1
            continue
        idx[source_name] += 1
        conv_id = make_id(source_name, title, idx[source_name])
        write_conversation(conv_id, source_name, title, messages, OUTPUT_DIR)
        stats[f'{source_name}_kept'] += 1

# Claude April
print("Processing Claude April...")
with zipfile.ZipFile(EXPORTS_DIR / 'claude_april.zip') as z:
    with z.open('conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        stats['claude_april_total'] += 1
        title = c.get('name') or 'untitled'
        messages = extract_claude_user_messages(c)
        if len(messages) <= 1:
            stats['filtered_single_msg'] += 1
            continue
        idx['claude_april'] += 1
        conv_id = make_id('claude_april', title, idx['claude_april'])
        write_conversation(conv_id, 'claude_april', title, messages, OUTPUT_DIR)
        stats['claude_april_kept'] += 1

# Claude Code
print("Processing Claude Code...")
cc_sessions = list((EXPORTS_DIR / 'claude_code_april').rglob('*.jsonl'))
for session_path in cc_sessions:
    stats['cc_total'] += 1
    messages = extract_cc_user_messages(session_path)
    if is_cc_definitely_not_learning(messages):
        stats['filtered_cc_too_short'] += 1
        continue
    idx['cc'] += 1
    title = session_path.parent.name
    conv_id = make_id('claude_code', session_path.stem, idx['cc'])
    write_conversation(conv_id, 'claude_code', title, messages, OUTPUT_DIR)
    stats['cc_kept'] += 1

# ── Summary ─────────────────────────────────────────────────────────
total_kept = sum(v for k, v in stats.items() if k.endswith('_kept'))
output_files = list(OUTPUT_DIR.glob('*.json'))

print(f"\n{'='*65}")
print("PREPROCESSING COMPLETE")
print(f"{'='*65}")
print(f"  Output directory: {OUTPUT_DIR}")
print(f"  Files written: {len(output_files)}")
print(f"  Total conversations kept: {total_kept}")
print()
print("  Source breakdown:")
for key, val in sorted(stats.items()):
    print(f"    {key}: {val}")
print()

total_tokens = 0
for f in output_files:
    with open(f) as fh:
        data = json.load(fh)
    total_tokens += data['metadata']['total_chars'] / 4

print(f"  Total user-only tokens: {total_tokens:,.0f} ({total_tokens/1e6:.2f} MTok)")
print(f"  Avg tokens per conversation: {total_tokens/len(output_files):,.0f}")
print(f"\n  Ready for extraction harness: ./extraction_harness.sh -i {OUTPUT_DIR} -o OUTPUT_DIR")

