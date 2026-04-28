#!/usr/bin/env python3
"""
Temporal Learning Arc Analysis

Maps how Andrew's learning interests evolved over time.
Uses the preprocessed conversations with timestamps from original sources.
"""
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

EXPORTS_DIR = Path.home() / "ai-exports"

# Domain detection via keyword presence
DOMAINS = {
    'python': ['python', 'numpy', 'pandas', 'matplotlib', 'pytorch', 'flask', 'fastapi', 'def ', 'import ', 'class '],
    'java': ['java', 'public static', 'void', 'string[]', '.class', 'arraylist', 'hashmap', 'extends'],
    'finance': ['stock', 'portfolio', 'return', 'risk', 'volatility', 'market', 'trading', 'hedge', 'dividend', 'yield'],
    'probability': ['probability', 'random variable', 'distribution', 'expected value', 'variance', 'bayes'],
    'linear_algebra': ['matrix', 'vector', 'eigenvalue', 'linear transformation', 'determinant', 'basis'],
    'calculus': ['derivative', 'integral', 'limit', 'continuity', 'gradient', 'taylor'],
    'philosophy': ['epistemology', 'ontology', 'ethics', 'consciousness', 'free will', 'moral', 'existential'],
    'ai_ml': ['neural network', 'machine learning', 'transformer', 'attention', 'embedding', 'llm', 'gpt', 'claude'],
    'web_dev': ['react', 'html', 'css', 'javascript', 'component', 'api endpoint', 'dom', 'fetch'],
    'physics': ['force', 'mass', 'acceleration', 'gravity', 'energy', 'momentum', 'quantum', 'relativity'],
}


def get_domains(text):
    text_lower = text.lower()
    found = []
    for domain, keywords in DOMAINS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits >= 2:
            found.append(domain)
    return found


# ── Load ChatGPT with timestamps ───────────────────────────────────
monthly = defaultdict(lambda: defaultdict(int))  # (year, month) -> domain -> count
monthly_convos = defaultdict(int)

print("Loading ChatGPT with timestamps...")
with zipfile.ZipFile(EXPORTS_DIR / 'chatgpt_feb.zip') as z:
    conv_files = sorted([f for f in z.namelist() if 'conversations-' in f and f.endswith('.json')])
    for cf in conv_files:
        with z.open(cf) as f:
            convos = json.load(f)
        for c in convos:
            ts = c.get('create_time')
            if not ts:
                continue
            try:
                dt = datetime.fromtimestamp(ts)
            except:
                continue
            
            mapping = c.get('mapping', {})
            user_text = ''
            user_count = 0
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
                    user_text += ' ' + text
                    user_count += 1
            
            if user_count < 2:
                continue
            
            key = (dt.year, dt.month)
            monthly_convos[key] += 1
            
            domains = get_domains(user_text)
            for d in domains:
                monthly[key][d] += 1

# Claude sources
for source_name in ['claude_acc1_feb', 'claude_acc2_feb']:
    print(f"Loading {source_name}...")
    with open(EXPORTS_DIR / source_name / 'conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        created = c.get('created_at', '')
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace('Z', '+00:00')).replace(tzinfo=None)
        except:
            continue
        
        user_text = ''
        user_count = 0
        for m in c.get('chat_messages', []):
            if m.get('sender') != 'human':
                continue
            text = ''
            if isinstance(m.get('text'), str):
                text = m['text']
            elif isinstance(m.get('content'), list):
                text = ' '.join(p.get('text', '') for p in m['content']
                               if isinstance(p, dict) and 'text' in p)
            if text.strip():
                user_text += ' ' + text
                user_count += 1
        
        if user_count < 2:
            continue
        
        key = (dt.year, dt.month)
        monthly_convos[key] += 1
        domains = get_domains(user_text)
        for d in domains:
            monthly[key][d] += 1

# Claude April
print("Loading Claude April...")
with zipfile.ZipFile(EXPORTS_DIR / 'claude_april.zip') as z:
    with z.open('conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        created = c.get('created_at', '')
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace('Z', '+00:00')).replace(tzinfo=None)
        except:
            continue
        
        user_text = ''
        user_count = 0
        for m in c.get('chat_messages', []):
            if m.get('sender') != 'human':
                continue
            text = ''
            if isinstance(m.get('text'), str):
                text = m['text']
            elif isinstance(m.get('content'), list):
                text = ' '.join(p.get('text', '') for p in m['content']
                               if isinstance(p, dict) and 'text' in p)
            if text.strip():
                user_text += ' ' + text
                user_count += 1
        
        if user_count < 2:
            continue
        
        key = (dt.year, dt.month)
        monthly_convos[key] += 1
        domains = get_domains(user_text)
        for d in domains:
            monthly[key][d] += 1


# ── Timeline display ───────────────────────────────────────────────
all_months = sorted(monthly_convos.keys())
all_domains = sorted(set(d for m in monthly.values() for d in m.keys()))

print(f"\n{'='*90}")
print("TEMPORAL LEARNING ARC — Monthly Domain Heat Map")
print(f"{'='*90}")

# Header
header = f"{'Month':<10} {'Conv':>4} "
for d in all_domains:
    header += f" {d[:6]:>6}"
print(header)
print("-" * len(header))

for key in all_months:
    year, month = key
    label = f"{year}-{month:02d}"
    total = monthly_convos[key]
    row = f"{label:<10} {total:>4} "
    for d in all_domains:
        count = monthly[key].get(d, 0)
        if count == 0:
            row += f"{'·':>7}"
        elif count <= 2:
            row += f"{'░':>7}"
        elif count <= 5:
            row += f"{'▒':>7}"
        elif count <= 10:
            row += f"{'▓':>7}"
        else:
            row += f"{'█':>7}"
    print(row)

# ── Quarter-level summary ──────────────────────────────────────────
print(f"\n\n{'='*90}")
print("QUARTERLY DOMAIN DOMINANCE")
print(f"{'='*90}")

quarterly = defaultdict(lambda: Counter())
quarterly_total = Counter()

for (year, month), domains in monthly.items():
    q = (month - 1) // 3 + 1
    qkey = f"{year}Q{q}"
    for d, count in domains.items():
        quarterly[qkey][d] += count
    quarterly_total[qkey] += monthly_convos[(year, month)]

for qkey in sorted(quarterly.keys()):
    total = quarterly_total[qkey]
    top = quarterly[qkey].most_common(3)
    top_str = ', '.join(f"{d}({c})" for d, c in top)
    print(f"  {qkey}: {total:>3} conversations — {top_str}")

# ── Learning trajectory narrative ───────────────────────────────────
print(f"\n\n{'='*90}")
print("LEARNING TRAJECTORY NARRATIVE")
print(f"{'='*90}")

narratives = []
for qkey in sorted(quarterly.keys()):
    top = quarterly[qkey].most_common(3)
    total = quarterly_total[qkey]
    if total < 3:
        continue
    dominant = top[0][0] if top else 'unknown'
    secondary = top[1][0] if len(top) > 1 else None
    
    entry = f"  {qkey} ({total} convos): "
    if dominant == 'java':
        entry += "CS coursework (Java fundamentals)"
    elif dominant == 'finance':
        if secondary == 'python':
            entry += "Algorithmic trading (finance + Python programming)"
        else:
            entry += "Financial markets exploration"
    elif dominant == 'python':
        if secondary == 'finance':
            entry += "Trading algorithm development (Python + finance)"
        else:
            entry += "Python programming skill building"
    elif dominant == 'probability':
        entry += "Statistics and probability theory"
    elif dominant == 'web_dev':
        entry += "Web development projects"
    elif dominant == 'ai_ml':
        entry += "AI/ML exploration and projects"
    elif dominant == 'physics':
        entry += "Physics concepts from first principles"
    elif dominant == 'philosophy':
        entry += "Philosophical inquiry"
    elif dominant == 'calculus':
        entry += "Calculus coursework"
    elif dominant == 'linear_algebra':
        entry += "Linear algebra"
    else:
        entry += f"Mixed ({dominant})"
    
    narratives.append(entry)

for n in narratives:
    print(n)

