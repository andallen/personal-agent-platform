#!/usr/bin/env python3
"""
TF-IDF Topic Clustering Experiment

Uses TF-IDF vectorization + KMeans clustering to discover natural topic
groupings in the conversation corpus. This is completely free (no API calls)
and can discover topics the keyword-based approach misses.

Compares results to our keyword-based domain classification.
"""
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.decomposition import TruncatedSVD

EXPORTS_DIR = Path.home() / "ai-exports"


def extract_user_text(conv, source_type):
    """Extract concatenated user text from a conversation."""
    texts = []
    if source_type == 'chatgpt':
        mapping = conv.get('mapping', {})
        for node in mapping.values():
            msg = node.get('message')
            if msg and msg.get('author', {}).get('role') == 'user':
                parts = msg.get('content', {}).get('parts', [])
                text = ' '.join(str(p) for p in parts if isinstance(p, str))
                if text.strip():
                    texts.append(text.strip())
    elif source_type == 'claude':
        for m in conv.get('chat_messages', []):
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
                    texts.append(text.strip())
    return ' '.join(texts)


# ── Load conversations ──────────────────────────────────────────────
conversations = []

print("Loading ChatGPT...")
with zipfile.ZipFile(EXPORTS_DIR / 'chatgpt_feb.zip') as z:
    conv_files = sorted([f for f in z.namelist() if 'conversations-' in f and f.endswith('.json')])
    for cf in conv_files:
        with z.open(cf) as f:
            convos = json.load(f)
        for c in convos:
            text = extract_user_text(c, 'chatgpt')
            if len(text) > 100:
                conversations.append({
                    'title': c.get('title', 'untitled'),
                    'text': text,
                    'source': 'chatgpt',
                })

for source in ['claude_acc1_feb', 'claude_acc2_feb']:
    print(f"Loading {source}...")
    with open(EXPORTS_DIR / source / 'conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        text = extract_user_text(c, 'claude')
        if len(text) > 100:
            conversations.append({
                'title': c.get('name') or 'untitled',
                'text': text,
                'source': source,
            })

print("Loading Claude April...")
with zipfile.ZipFile(EXPORTS_DIR / 'claude_april.zip') as z:
    with z.open('conversations.json') as f:
        convos = json.load(f)
    for c in convos:
        text = extract_user_text(c, 'claude')
        if len(text) > 100:
            conversations.append({
                'title': c.get('name') or 'untitled',
                'text': text,
                'source': 'claude_april',
            })

print(f"\nLoaded {len(conversations)} conversations with >100 chars user text")

# ── TF-IDF Vectorization ───────────────────────────────────────────
print("\nVectorizing with TF-IDF...")
texts = [c['text'] for c in conversations]

vectorizer = TfidfVectorizer(
    max_features=5000,
    min_df=3,
    max_df=0.5,
    stop_words='english',
    ngram_range=(1, 2),
    sublinear_tf=True,
)
tfidf_matrix = vectorizer.fit_transform(texts)
feature_names = vectorizer.get_feature_names_out()
print(f"  TF-IDF matrix shape: {tfidf_matrix.shape}")

# ── Dimensionality reduction for visualization ─────────────────────
print("\nReducing dimensions with SVD...")
svd = TruncatedSVD(n_components=50, random_state=42)
reduced = svd.fit_transform(tfidf_matrix)
print(f"  Explained variance (50 components): {svd.explained_variance_ratio_.sum():.1%}")

# ── KMeans clustering ───────────────────────────────────────────────
# Try multiple K values to find optimal
print("\nTesting cluster counts...")
inertias = []
for k in [10, 15, 20, 25, 30, 40]:
    km = MiniBatchKMeans(n_clusters=k, random_state=42, batch_size=500)
    km.fit(reduced)
    inertias.append((k, km.inertia_))
    print(f"  K={k}: inertia={km.inertia_:.0f}")

# Use K=25 as a good middle ground
K = 25
print(f"\nClustering with K={K}...")
km = MiniBatchKMeans(n_clusters=K, random_state=42, batch_size=500)
labels = km.fit_predict(reduced)

# ── Analyze clusters ────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"CLUSTER ANALYSIS (K={K})")
print("=" * 70)

for cluster_id in range(K):
    members = [i for i, l in enumerate(labels) if l == cluster_id]
    if len(members) < 3:
        continue
    
    # Get top terms for this cluster
    cluster_tfidf = tfidf_matrix[members].mean(axis=0)
    cluster_arr = np.asarray(cluster_tfidf).flatten()
    top_term_indices = cluster_arr.argsort()[-10:][::-1]
    top_terms = [(feature_names[i], cluster_arr[i]) for i in top_term_indices]
    
    # Get representative titles
    titles = [conversations[i]['title'] for i in members[:8]]
    sources = Counter(conversations[i]['source'] for i in members)
    
    print(f"\n  Cluster {cluster_id} — {len(members)} conversations")
    print(f"    Sources: {dict(sources)}")
    print(f"    Top terms: {', '.join(f'{t[0]}({t[1]:.3f})' for t in top_terms[:7])}")
    print(f"    Sample titles:")
    for t in titles[:5]:
        print(f"      • {t[:70]}")

# ── Compare to keyword-based classification ─────────────────────────
print("\n\n" + "=" * 70)
print("DISCOVERED TOPICS vs KEYWORD-BASED CLASSIFICATION")
print("=" * 70)

# Label clusters by their most distinctive terms
cluster_labels = {}
for cluster_id in range(K):
    members = [i for i, l in enumerate(labels) if l == cluster_id]
    if not members:
        continue
    cluster_tfidf = tfidf_matrix[members].mean(axis=0)
    cluster_arr = np.asarray(cluster_tfidf).flatten()
    top_idx = cluster_arr.argsort()[-3:][::-1]
    label = ' + '.join(feature_names[i] for i in top_idx)
    cluster_labels[cluster_id] = label

# Cluster size distribution
sizes = Counter(labels)
print("\nCluster sizes (sorted):")
for cid, count in sizes.most_common():
    label = cluster_labels.get(cid, '?')
    print(f"  [{cid:2d}] {count:>4} conversations — {label}")

# ── Topic diversity per conversation ────────────────────────────────
print("\n\n" + "=" * 70)
print("CONVERSATIONS THAT DON'T FIT ANY CLUSTER WELL")
print("=" * 70)
print("(These are unique/cross-domain — may need special extraction handling)")

# Find conversations with low max similarity to any cluster center
distances = km.transform(reduced)  # distance to each cluster center
min_distances = distances.min(axis=1)
outlier_indices = min_distances.argsort()[-20:][::-1]

for idx in outlier_indices:
    conv = conversations[idx]
    dist = min_distances[idx]
    cluster = labels[idx]
    print(f"  dist={dist:.2f} cluster={cluster} [{conv['source']:<12}] {conv['title'][:60]}")

# ── Summary ─────────────────────────────────────────────────────────
print(f"\n\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"  Total conversations clustered: {len(conversations)}")
print(f"  Number of clusters: {K}")
print(f"  Vocabulary size: {len(feature_names)}")
print(f"  SVD explained variance: {svd.explained_variance_ratio_.sum():.1%}")

# What did TF-IDF find that keywords missed?
print(f"\n  Topics that TF-IDF discovered beyond keyword categories:")
print(f"  (Look for clusters whose top terms don't match our predefined domains)")
for cid in range(K):
    members = [i for i, l in enumerate(labels) if l == cid]
    if len(members) < 5:
        continue
    label = cluster_labels.get(cid, '?')
    # Check if any keyword domain terms appear
    keyword_domains = ['probability', 'matrix', 'derivative', 'neural', 'python',
                       'javascript', 'stock', 'ethics', 'measure']
    terms = label.lower()
    if not any(kw in terms for kw in keyword_domains):
        print(f"  → Cluster {cid} ({len(members)} convos): {label}")

