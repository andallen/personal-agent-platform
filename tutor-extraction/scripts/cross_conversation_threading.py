#!/usr/bin/env python3
"""
Cross-Conversation Topic Threading Experiment

Detects topics that span multiple conversations by:
1. Extracting n-grams and domain terms from each conversation
2. Building a co-occurrence matrix of terms across conversations
3. Identifying "topic threads" — sequences of conversations revisiting the same topic
4. Measuring temporal spacing between revisits

This reveals learning patterns like spaced repetition, spiral learning,
and topic obsession arcs.
"""
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

EXPORTS_DIR = Path.home() / "ai-exports"

# Domain-specific term dictionaries for better topic detection
DOMAIN_TERMS = {
    'probability': ['probability', 'bayes', 'conditional', 'random variable', 'distribution',
                    'expected value', 'variance', 'bernoulli', 'binomial', 'poisson', 'normal distribution',
                    'central limit', 'law of large numbers', 'markov', 'stochastic'],
    'linear_algebra': ['matrix', 'matrices', 'vector', 'eigenvalue', 'eigenvector', 'linear transformation',
                       'determinant', 'rank', 'null space', 'column space', 'basis', 'dimension',
                       'orthogonal', 'projection', 'svd', 'singular value'],
    'calculus': ['derivative', 'integral', 'limit', 'continuity', 'differentiable', 'gradient',
                 'partial derivative', 'chain rule', 'taylor series', 'convergence', 'divergence'],
    'measure_theory': ['sigma algebra', 'measure', 'measurable', 'borel', 'lebesgue', 'almost everywhere',
                       'countable additivity', 'outer measure'],
    'machine_learning': ['neural network', 'gradient descent', 'backpropagation', 'loss function',
                         'overfitting', 'regularization', 'training', 'validation', 'test set',
                         'classification', 'regression', 'transformer', 'attention mechanism',
                         'embedding', 'fine-tuning', 'reinforcement learning'],
    'python': ['python', 'numpy', 'pandas', 'matplotlib', 'pytorch', 'tensorflow', 'flask',
               'django', 'fastapi', 'decorator', 'generator', 'list comprehension', 'async await'],
    'javascript': ['javascript', 'react', 'node', 'typescript', 'dom', 'css', 'html',
                   'component', 'useState', 'useEffect', 'api endpoint', 'fetch', 'promise'],
    'finance': ['stock', 'option', 'bond', 'portfolio', 'return', 'risk', 'volatility',
                'sharpe', 'alpha', 'beta', 'hedge', 'derivative', 'futures', 'market',
                'dividend', 'compound interest', 'present value', 'dcf'],
    'philosophy': ['epistemology', 'ontology', 'metaphysics', 'ethics', 'consciousness',
                   'free will', 'determinism', 'moral', 'virtue', 'justice', 'existential',
                   'phenomenology', 'a priori', 'empiricism', 'rationalism'],
}

def extract_user_text(conversation, source_type):
    """Extract user text and metadata from a conversation."""
    messages = []
    timestamp = None

    if source_type == 'chatgpt':
        title = conversation.get('title', 'untitled')
        create_time = conversation.get('create_time')
        if create_time:
            try:
                timestamp = datetime.fromtimestamp(create_time)
            except:
                pass
        mapping = conversation.get('mapping', {})
        for node_id, node in mapping.items():
            msg = node.get('message')
            if msg and msg.get('author', {}).get('role') == 'user':
                parts = msg.get('content', {}).get('parts', [])
                text = ' '.join(str(p) for p in parts if isinstance(p, str))
                if text.strip():
                    messages.append(text.strip())

    elif source_type == 'claude':
        title = conversation.get('name', 'untitled')
        created = conversation.get('created_at', '')
        if created:
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00")); timestamp = ts.replace(tzinfo=None)
            except:
                pass
        for m in conversation.get('chat_messages', []):
            if m.get('sender') == 'human':
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

    return {
        'title': title,
        'messages': messages,
        'text': ' '.join(messages).lower(),
        'timestamp': timestamp,
        'source': source_type,
        'num_messages': len(messages),
    }


def detect_topics(text):
    """Detect domain topics present in conversation text."""
    found = {}
    for domain, terms in DOMAIN_TERMS.items():
        hits = 0
        matched_terms = []
        for term in terms:
            count = text.count(term.lower())
            if count > 0:
                hits += count
                matched_terms.append(term)
        if hits >= 2:  # require at least 2 hits to count
            found[domain] = {'hits': hits, 'terms': matched_terms}
    return found


def extract_key_bigrams(text, min_count=2):
    """Extract meaningful bigrams (2-word phrases) from text."""
    words = re.findall(r'[a-z]+', text)
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                  'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                  'could', 'should', 'may', 'might', 'can', 'shall', 'to', 'of',
                  'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                  'through', 'during', 'before', 'after', 'above', 'below',
                  'between', 'out', 'up', 'down', 'and', 'but', 'or', 'nor',
                  'not', 'so', 'yet', 'if', 'then', 'than', 'that', 'this',
                  'it', 'its', 'i', 'me', 'my', 'we', 'our', 'you', 'your',
                  'he', 'she', 'they', 'them', 'his', 'her', 'what', 'which',
                  'who', 'whom', 'how', 'when', 'where', 'why', 'all', 'each',
                  'every', 'both', 'few', 'more', 'most', 'other', 'some',
                  'such', 'no', 'only', 'own', 'same', 'just', 'also', 'very',
                  'like', 'about', 'there', 'here', 'am', 'get', 'got', 'one',
                  'two', 'first', 'new', 'way', 'think', 'know', 'want',
                  'because', 'any', 'these', 'those', 'give', 'make', 'use'}
    bigrams = []
    for i in range(len(words) - 1):
        if words[i] not in stop_words and words[i+1] not in stop_words and \
           len(words[i]) > 2 and len(words[i+1]) > 2:
            bigrams.append(f"{words[i]} {words[i+1]}")
    counts = Counter(bigrams)
    return {bg: c for bg, c in counts.items() if c >= min_count}


# ── Load all conversations ─────────────────────────────────────────
all_convos = []

# ChatGPT
print("Loading ChatGPT...")
with zipfile.ZipFile(EXPORTS_DIR / 'chatgpt_feb.zip') as z:
    conv_files = sorted([f for f in z.namelist() if 'conversations-' in f and f.endswith('.json')])
    for cf in conv_files:
        with z.open(cf) as f:
            convos = json.load(f)
        for c in convos:
            extracted = extract_user_text(c, 'chatgpt')
            if extracted['num_messages'] >= 2 and len(extracted['text']) > 50:
                all_convos.append(extracted)

# Claude
for source_name in ['claude_acc1_feb', 'claude_acc2_feb']:
    print(f"Loading {source_name}...")
    with open(EXPORTS_DIR / source_name / 'conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        extracted = extract_user_text(c, 'claude')
        if extracted['num_messages'] >= 2 and len(extracted['text']) > 50:
            all_convos.append(extracted)

# Claude April
print("Loading Claude April...")
with zipfile.ZipFile(EXPORTS_DIR / 'claude_april.zip') as z:
    with z.open('conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        extracted = extract_user_text(c, 'claude')
        if extracted['num_messages'] >= 2 and len(extracted['text']) > 50:
            all_convos.append(extracted)

print(f"Loaded {len(all_convos)} multi-message conversations")

# ── Detect topics per conversation ──────────────────────────────────
for conv in all_convos:
    conv['topics'] = detect_topics(conv['text'])
    conv['bigrams'] = extract_key_bigrams(conv['text'])

# ── Build topic threads ─────────────────────────────────────────────
# Sort by timestamp where available
dated = [c for c in all_convos if c['timestamp']]
undated = [c for c in all_convos if not c['timestamp']]
dated.sort(key=lambda c: c['timestamp'])

print(f"\nDated conversations: {len(dated)}")
print(f"Undated conversations: {len(undated)}")

# Topic thread analysis
topic_threads = defaultdict(list)  # topic -> list of (timestamp, title, hits)
for conv in dated:
    for topic, info in conv['topics'].items():
        topic_threads[topic].append({
            'timestamp': conv['timestamp'],
            'title': conv['title'],
            'hits': info['hits'],
            'terms': info['terms'],
            'source': conv['source'],
        })

print("\n" + "=" * 70)
print("TOPIC THREADS (topics spanning multiple conversations, chronological)")
print("=" * 70)

for topic in sorted(topic_threads.keys(), key=lambda t: len(topic_threads[t]), reverse=True):
    thread = topic_threads[topic]
    if len(thread) < 3:
        continue

    print(f"\n{'─' * 60}")
    print(f"  {topic.upper()} — {len(thread)} conversations")
    print(f"{'─' * 60}")

    # Show first and last
    first = thread[0]
    last = thread[-1]
    span_days = (last['timestamp'] - first['timestamp']).days

    print(f"  Span: {first['timestamp'].strftime('%Y-%m-%d')} → {last['timestamp'].strftime('%Y-%m-%d')} ({span_days} days)")

    # Gap analysis
    gaps = []
    for i in range(1, len(thread)):
        gap = (thread[i]['timestamp'] - thread[i-1]['timestamp']).days
        gaps.append(gap)

    if gaps:
        avg_gap = sum(gaps) / len(gaps)
        max_gap = max(gaps)
        min_gap = min(gaps)
        print(f"  Return interval: avg {avg_gap:.0f} days, min {min_gap} days, max {max_gap} days")

    # Show density bursts (3+ conversations within 7 days)
    bursts = []
    i = 0
    while i < len(thread):
        burst = [thread[i]]
        j = i + 1
        while j < len(thread) and (thread[j]['timestamp'] - burst[0]['timestamp']).days <= 7:
            burst.append(thread[j])
            j += 1
        if len(burst) >= 3:
            bursts.append(burst)
        i = j if j > i + 1 else i + 1
    if bursts:
        print(f"  Learning bursts (3+ convos in 7 days): {len(bursts)}")
        for burst in bursts[:3]:
            dates = f"{burst[0]['timestamp'].strftime('%m/%d')}–{burst[-1]['timestamp'].strftime('%m/%d/%Y')}"
            print(f"    • {dates}: {len(burst)} conversations")

    # Show first 5 and last 3
    show = thread[:5]
    print(f"  First 5:")
    for t in show:
        print(f"    [{t['timestamp'].strftime('%Y-%m-%d')}] [{t['source']:<7}] {t['title'][:55]} ({t['hits']} hits)")
    if len(thread) > 8:
        print(f"    ... {len(thread) - 8} more ...")
    if len(thread) > 5:
        print(f"  Last 3:")
        for t in thread[-3:]:
            print(f"    [{t['timestamp'].strftime('%Y-%m-%d')}] [{t['source']:<7}] {t['title'][:55]} ({t['hits']} hits)")


# ── Cross-topic co-occurrence ───────────────────────────────────────
print("\n\n" + "=" * 70)
print("TOPIC CO-OCCURRENCE (which topics appear together)")
print("=" * 70)

cooccur = Counter()
for conv in all_convos:
    topics = list(conv['topics'].keys())
    for i in range(len(topics)):
        for j in range(i+1, len(topics)):
            pair = tuple(sorted([topics[i], topics[j]]))
            cooccur[pair] += 1

for pair, count in cooccur.most_common(20):
    print(f"  {pair[0]:<20} + {pair[1]:<20} → {count} conversations")


# ── Shared bigram analysis (find non-obvious topic connections) ─────
print("\n\n" + "=" * 70)
print("CROSS-CONVERSATION BIGRAMS (phrases appearing in 5+ conversations)")
print("=" * 70)

bigram_convos = defaultdict(list)
for conv in all_convos:
    for bg in conv['bigrams']:
        bigram_convos[bg].append((conv.get('title') or 'untitled')[:50])

# Filter to bigrams appearing in 5+ conversations
frequent_bigrams = {bg: titles for bg, titles in bigram_convos.items() if len(titles) >= 5}

# Sort by frequency
for bg, titles in sorted(frequent_bigrams.items(), key=lambda x: len(x[1]), reverse=True)[:40]:
    print(f"  \"{bg}\" — {len(titles)} conversations")
    for t in titles[:3]:
        print(f"    • {t}")
    if len(titles) > 3:
        print(f"    ... +{len(titles)-3} more")


# ── Title-based topic clustering ────────────────────────────────────
print("\n\n" + "=" * 70)
print("TITLE-BASED SERIES DETECTION (numbered or recurring title patterns)")
print("=" * 70)

title_patterns = defaultdict(list)
for conv in all_convos:
    title = conv.get('title') or 'untitled'
    # Strip trailing numbers/parens
    base = re.sub(r'\s*[\(\[]?\d+[\)\]]?\s*$', '', title)
    base = re.sub(r'\s*\(continued\)\s*$', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\s*part\s*\d+\s*$', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\s*cont\.?\s*$', '', base, flags=re.IGNORECASE)
    if base != title or len(base) > 5:
        title_patterns[base.strip().lower()].append(conv)

series = {base: convos for base, convos in title_patterns.items() if len(convos) >= 2}
for base, convos in sorted(series.items(), key=lambda x: len(x[1]), reverse=True)[:25]:
    sources = set(c['source'] for c in convos)
    dates = [c['timestamp'].strftime('%Y-%m-%d') if c['timestamp'] else '?' for c in convos]
    print(f"  \"{base}\" — {len(convos)} conversations ({', '.join(sources)})")
    for c in convos[:5]:
        ts = c['timestamp'].strftime('%Y-%m-%d') if c['timestamp'] else '?'
        print(f"    [{ts}] {c['title'][:60]} ({c['num_messages']} msgs)")
    if len(convos) > 5:
        print(f"    ... +{len(convos)-5} more")


# ── Summary statistics ──────────────────────────────────────────────
print("\n\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

total_with_topics = sum(1 for c in all_convos if c['topics'])
print(f"  Conversations with detected domain topics: {total_with_topics}/{len(all_convos)} ({total_with_topics/len(all_convos)*100:.1f}%)")
print(f"  Topic threads with 3+ conversations: {sum(1 for t in topic_threads.values() if len(t) >= 3)}")
print(f"  Topic threads with 10+ conversations: {sum(1 for t in topic_threads.values() if len(t) >= 10)}")
print(f"  Title-based series with 2+ conversations: {len(series)}")
print(f"  Title-based series with 3+ conversations: {sum(1 for s in series.values() if len(s) >= 3)}")

# For the extraction pipeline: how many conversations are part of a topic thread?
in_thread = set()
for topic, thread in topic_threads.items():
    if len(thread) >= 3:
        for t in thread:
            in_thread.add(t['title'])
print(f"  Conversations participating in topic threads: {len(in_thread)} (extraction should note thread membership)")

