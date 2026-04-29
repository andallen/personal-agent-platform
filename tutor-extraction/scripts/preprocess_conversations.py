#!/usr/bin/env python3
"""
Phase 0: Preprocess Raw Exports → Individual Conversation Files

Takes raw AI conversation exports from ~/ai-exports/ and produces
individual JSON files ready for the extraction harness.

Each output file: {id, source, title, user_messages, metadata}

Applies all programmatic filters:
1. Drop 1-message conversations
2. Drop stock research template conversations
3. Drop image generation conversations
4. Drop too-short Claude Code sessions (0-1 user messages)
"""
import json
import hashlib
import re
import zipfile
from collections import Counter
from datetime import datetime
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
    t = title.lower()
    if 'image' in t and ('generat' in t or 'request' in t or 'creat' in t):
        return True
    if t.startswith('created gemini canvas'):
        return True
    if 'draw ' in t or 'make me a picture' in t or 'generate a photo' in t:
        return True
    return False


def extract_chatgpt_messages(conv):
    mapping = conv.get('mapping', {})
    nodes = []
    for node in mapping.values():
        msg = node.get('message')
        if msg is None:
            continue
        author = msg.get('author', {})
        role = author.get('role')
        if role not in ('user', 'assistant'):
            continue
        parts = msg.get('content', {}).get('parts', [])
        text = ' '.join(str(p) for p in parts if isinstance(p, str))
        if text.strip():
            ts = msg.get('create_time', 0) or 0
            nodes.append({'role': role, 'text': text.strip(), 'ts': ts})
    nodes.sort(key=lambda x: x['ts'])
    return [{'role': n['role'], 'text': n['text']} for n in nodes]


def extract_claude_messages(conv):
    messages = []
    for m in conv.get('chat_messages', []):
        sender = m.get('sender')
        if sender == 'human':
            role = 'user'
        elif sender == 'assistant':
            role = 'assistant'
        else:
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
            messages.append({'role': role, 'text': text.strip()})
    return messages


def extract_cc_messages(jsonl_path):
    messages = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                entry_type = entry.get('type')
                if entry_type not in ('user', 'assistant'):
                    continue
                if entry.get('isMeta', False):
                    continue
                content = entry.get('message', {}).get('content', '')
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = ' '.join(p.get('text', '') for p in content
                                   if isinstance(p, dict) and p.get('type') == 'text')
                else:
                    continue
                if entry_type == 'user':
                    if text.startswith('<command-name>') or text.startswith('/'):
                        continue
                    if text.startswith('<local-command-stdout>'):
                        continue
                text = text.strip()
                if text:
                    role = 'user' if entry_type == 'user' else 'assistant'
                    messages.append({'role': role, 'text': text})
    except Exception:
        return []
    return messages


def is_cc_definitely_not_learning(messages):
    """Returns True only if we can PROVE this session has no learning.
    Only condition: 0-1 user messages (no arc possible)."""
    user_count = sum(1 for m in messages if m['role'] == 'user')
    return user_count < 2


GEMINI_CONVERSATION_GAP_SECONDS = 1800  # 30 minutes


def parse_gemini_html(html_content):
    """Parse Gemini Takeout HTML into a list of (user_text, timestamp) pairs.

    Gemini exports a flat activity log — individual prompt/response pairs,
    not grouped conversations. Each outer-cell div contains one exchange.
    """
    entries = html_content.split(
        'outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp'
    )[1:]

    parsed = []
    for entry in entries:
        m = re.search(
            r'mdl-typography--body-1">(.*?)</div>', entry, re.DOTALL
        )
        if not m:
            continue
        raw = m.group(1)
        text = re.sub(r'<[^>]+>', ' ', raw).strip()
        text = re.sub(r'\s+', ' ', text)

        parts = re.split(
            r'(\w+ \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s*[AP]M)', text
        )
        user_prompt = parts[0].strip() if parts else ''
        date_str = parts[1].strip() if len(parts) > 1 else ''

        if user_prompt.startswith('Prompted '):
            user_prompt = user_prompt[len('Prompted '):]
        elif user_prompt.startswith('Created Gemini Canvas'):
            pass  # keep as-is for filter to catch

        ts = None
        if date_str:
            try:
                ts = datetime.strptime(date_str, '%b %d, %Y, %I:%M:%S %p')
            except ValueError:
                pass

        if user_prompt and ts:
            parsed.append({'text': user_prompt, 'timestamp': ts})

    parsed.sort(key=lambda x: x['timestamp'])
    return parsed


def reconstruct_gemini_conversations(entries, gap_seconds=GEMINI_CONVERSATION_GAP_SECONDS):
    """Group flat Gemini entries into conversations by timestamp proximity."""
    if not entries:
        return []

    conversations = [[entries[0]]]
    for entry in entries[1:]:
        gap = (entry['timestamp'] - conversations[-1][-1]['timestamp']).total_seconds()
        if gap > gap_seconds:
            conversations.append([entry])
        else:
            conversations[-1].append(entry)

    return conversations


def gemini_conversation_title(messages):
    """Generate a title from the first user message."""
    first = messages[0] if messages else ''
    if len(first) <= 60:
        return first
    return first[:57] + '...'


def write_conversation(conv_id, source, title, messages, output_dir):
    """Write a preprocessed conversation to disk."""
    output = {
        'id': conv_id,
        'source': source,
        'title': title,
        'messages': messages,
        'metadata': {
            'num_messages': len(messages),
            'user_messages': sum(1 for m in messages if m['role'] == 'user'),
            'total_chars': sum(len(m['text']) for m in messages),
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
            
            messages = extract_chatgpt_messages(c)
            user_count = sum(1 for m in messages if m['role'] == 'user')
            if user_count <= 1:
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
        messages = extract_claude_messages(c)
        user_count = sum(1 for m in messages if m['role'] == 'user')
        if user_count <= 1:
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
        messages = extract_claude_messages(c)
        user_count = sum(1 for m in messages if m['role'] == 'user')
        if user_count <= 1:
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
    messages = extract_cc_messages(session_path)
    if is_cc_definitely_not_learning(messages):
        stats['filtered_cc_too_short'] += 1
        continue
    idx['cc'] += 1
    title = session_path.parent.name
    conv_id = make_id('claude_code', session_path.stem, idx['cc'])
    write_conversation(conv_id, 'claude_code', title, messages, OUTPUT_DIR)
    stats['cc_kept'] += 1

# Gemini (Google Takeout)
print("Processing Gemini...")
with zipfile.ZipFile(EXPORTS_DIR / 'google_takeout_april.zip') as z:
    with z.open('Takeout/My Activity/Gemini Apps/MyActivity.html') as f:
        html_content = f.read().decode('utf-8', errors='replace')

gemini_entries = parse_gemini_html(html_content)
stats['gemini_entries_total'] = len(gemini_entries)

gemini_convos = reconstruct_gemini_conversations(gemini_entries)
stats['gemini_reconstructed'] = len(gemini_convos)

for conv_messages in gemini_convos:
    stats['gemini_total'] += 1
    raw_texts = [e['text'] for e in conv_messages]
    title = gemini_conversation_title(raw_texts)

    if is_stock_research(title):
        stats['filtered_stock'] += 1
        continue
    if is_image_generation(title):
        stats['filtered_image'] += 1
        continue

    if any(is_stock_research(m) for m in raw_texts):
        stats['filtered_stock'] += 1
        continue

    if len(raw_texts) <= 1:
        stats['filtered_single_msg'] += 1
        continue

    messages = [{'role': 'user', 'text': t} for t in raw_texts]
    idx['gemini'] += 1
    conv_id = make_id('gemini', title, idx['gemini'])
    write_conversation(conv_id, 'gemini', title, messages, OUTPUT_DIR)
    stats['gemini_kept'] += 1

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

total_chars = 0
for f in output_files:
    with open(f) as fh:
        data = json.load(fh)
    total_chars += data['metadata']['total_chars']

est_tokens = total_chars / 4
print(f"  Total chars: {total_chars:,} (~{est_tokens:,.0f} tokens, {est_tokens/1e6:.2f} MTok)")
print(f"  Avg tokens per conversation: {est_tokens/len(output_files):,.0f}")

