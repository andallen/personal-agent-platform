#!/usr/bin/env python3
"""
Learning Style Deep Analysis

Goes beyond basic keyword detection to identify Andrew's distinctive
learning behaviors from the preprocessed conversations.

Looks for:
- First-principles reasoning patterns
- Challenge-the-AI behavior (pushback, "that can't be right")
- Analogy-seeking ("it's like...")
- Socratic style (follow-up chains)
- Building connections across domains
- Self-correction ("wait, I think I was wrong")
- Meta-learning ("I learn better when...")
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CONV_DIR = Path.home() / "tutor-extraction" / "conversations"

# ── Distinctive behavior patterns ──────────────────────────────────
PATTERNS = {
    'pushback': {
        'patterns': [
            r"but that (doesn'?t|can'?t|wouldn'?t)",
            r"i (disagree|don'?t (agree|buy|think))",
            r"that (can'?t|doesn'?t) be right",
            r"you'?re (wrong|incorrect|mistaken)",
            r"(no|nope),? (that'?s|it'?s|because)",
            r"but (wait|hold on|actually)",
            r"i'?m not (sure|convinced|buying)",
            r"circular logic",
            r"that'?s not what i (asked|meant|said)",
        ],
        'description': 'Challenges AI claims or reasoning'
    },
    'first_principles': {
        'patterns': [
            r"from (scratch|basics|ground up|first principles|the beginning)",
            r"start (from|at) the (beginning|basics|foundation)",
            r"what('?s| is) the (underlying|fundamental|root|core)",
            r"(break|boil) (it|this) down",
            r"at (its|the) core",
            r"most (basic|fundamental|elemental)",
            r"if (we|i|you) (strip|remove|take) (away|out)",
        ],
        'description': 'Reasons from first principles'
    },
    'analogy_seeking': {
        'patterns': [
            r"(it'?s|that'?s|is it) (like|similar to|comparable)",
            r"(use|give|provide) (an? )?analogy",
            r"think of (it|this) (like|as)",
            r"in (other|simple|plain|layman) (words|terms)",
            r"explain (it )?(simply|like i'?m|to a|in simple)",
            r"pretend (i|you|we)",
            r"imagine (that|if|you|a)",
        ],
        'description': 'Seeks analogies and simplified explanations'
    },
    'cross_domain': {
        'patterns': [
            r"(is this|does this) (relate|connect|apply) to",
            r"(similar|same) (concept|idea|principle|thing) (in|as|to)",
            r"reminds me of",
            r"just like (in|how|when)",
            r"(connection|relationship|link) between .+ and",
            r"this is (basically|essentially|really) (the same|just)",
        ],
        'description': 'Connects concepts across domains'
    },
    'self_correction': {
        'patterns': [
            r"(wait|oh),? i (was|think i was|might be) wrong",
            r"actually,? (i think|maybe|never ?mind)",
            r"let me (rethink|reconsider|correct myself|take that back)",
            r"i (see|realize) (now|my mistake|what i did wrong)",
            r"(ok|okay),? so (i was|it'?s not|that'?s not)",
            r"my (bad|mistake|understanding was wrong)",
        ],
        'description': 'Corrects own reasoning'
    },
    'meta_learning': {
        'patterns': [
            r"i (learn|understand|get it|think) (better|best|more) when",
            r"(that|this) (explanation|approach|way of explaining) (helped|works|clicked)",
            r"(don'?t|please don'?t|stop) (just |)(give|tell|show) me (the answer|it)",
            r"explain (it |)(through|via|using) (the )?socratic",
            r"one (thing|concept|idea|topic|question) at a time",
            r"bite-sized",
            r"step by step",
            r"walk me through",
        ],
        'description': 'Reflects on own learning process'
    },
    'verification': {
        'patterns': [
            r"(am i|is (that|this|my)) (right|correct|understanding this|getting this)",
            r"correct me if i'?m wrong",
            r"does (this|that|my) (make sense|sound right|check out)",
            r"so (to|let me) (summarize|make sure|confirm|verify|check)",
            r"is (it|this) (true|accurate|valid) that",
            r"tell me if (this|i'?m|my)",
        ],
        'description': 'Checks own understanding explicitly'
    },
    'depth_seeking': {
        'patterns': [
            r"(but )?why (specifically|exactly|precisely|in particular)",
            r"(what|how) (specifically|exactly|precisely|in particular)",
            r"go deeper",
            r"(more|give me more) (detail|depth|specifics)",
            r"don'?t (simplify|dumb it down|oversimplify)",
            r"the (real|actual|true|deeper) (reason|answer|explanation)",
            r"i want to (really|actually|truly) understand",
        ],
        'description': 'Pushes for deeper explanations'
    },
}

COMPILED = {}
for cat, info in PATTERNS.items():
    COMPILED[cat] = [re.compile(p, re.IGNORECASE) for p in info['patterns']]


# ── Process all conversations ───────────────────────────────────────
conv_files = list(CONV_DIR.glob('*.json'))
print(f"Processing {len(conv_files)} conversations...")

all_hits = defaultdict(list)  # cat -> list of (conv_id, title, quote)
conv_styles = defaultdict(lambda: defaultdict(int))  # conv_id -> cat -> count
cat_counts = Counter()
cat_conv_counts = Counter()

for conv_path in conv_files:
    with open(conv_path) as f:
        conv = json.load(f)
    
    conv_id = conv['id']
    title = conv.get('title', 'untitled')
    messages = conv.get('user_messages', [])
    
    conv_cats = set()
    for msg in messages:
        for cat, patterns in COMPILED.items():
            for p in patterns:
                matches = p.findall(msg)
                if matches:
                    cat_counts[cat] += len(matches)
                    conv_styles[conv_id][cat] += len(matches)
                    conv_cats.add(cat)
                    # Store first match as example
                    if len(all_hits[cat]) < 30:
                        # Get surrounding context
                        match = p.search(msg)
                        start = max(0, match.start() - 20)
                        end = min(len(msg), match.end() + 80)
                        context = msg[start:end]
                        all_hits[cat].append((conv_id, title, context))
    
    for cat in conv_cats:
        cat_conv_counts[cat] += 1


# ── Results ─────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("DISTINCTIVE LEARNING BEHAVIORS")
print(f"{'='*70}")

for cat, count in cat_counts.most_common():
    desc = PATTERNS[cat]['description']
    n_convos = cat_conv_counts[cat]
    pct = n_convos / len(conv_files) * 100
    print(f"\n  {cat.upper()} — {desc}")
    print(f"    {count} instances across {n_convos} conversations ({pct:.1f}%)")
    print(f"    Example quotes:")
    for _, title, quote in all_hits[cat][:5]:
        print(f"      [{title[:35]:<35}] \"{quote.strip()[:90]}\"")

# ── Conversations with the most distinctive behaviors ───────────────
print(f"\n\n{'='*70}")
print("MOST BEHAVIORALLY RICH CONVERSATIONS")
print(f"{'='*70}")

# Score each conversation by total distinctive behavior count
conv_behavior_scores = {}
for conv_id, cats in conv_styles.items():
    score = sum(cats.values())
    diversity = len(cats)
    conv_behavior_scores[conv_id] = (score, diversity, cats)

# Load titles for display
conv_titles = {}
for conv_path in conv_files:
    with open(conv_path) as f:
        conv = json.load(f)
    conv_titles[conv['id']] = conv.get('title', 'untitled')

top_behavioral = sorted(conv_behavior_scores.items(), 
                        key=lambda x: (x[1][1], x[1][0]), reverse=True)[:20]

for conv_id, (score, diversity, cats) in top_behavioral:
    title = conv_titles.get(conv_id, '?')
    cat_summary = ', '.join(f"{k}:{v}" for k, v in sorted(cats.items(), key=lambda x: -x[1])[:4])
    print(f"  [{diversity} types, {score} hits] {title[:50]} — {cat_summary}")


# ── Learning style profile ──────────────────────────────────────────
print(f"\n\n{'='*70}")
print("LEARNING STYLE PROFILE SUMMARY")
print(f"{'='*70}")

total_behaviors = sum(cat_counts.values())
for cat, count in cat_counts.most_common():
    pct = count / total_behaviors * 100
    bar = "█" * int(pct)
    print(f"  {cat:<20} {count:>5} ({pct:>5.1f}%) {bar}")

# Distinctive patterns
print(f"\n  Key insights:")
if cat_counts.get('pushback', 0) > cat_counts.get('verification', 0):
    print(f"    → More likely to CHALLENGE than VERIFY — adversarial learning style")
else:
    print(f"    → More likely to VERIFY than CHALLENGE — confirmatory learning style")

if cat_counts.get('analogy_seeking', 0) > cat_counts.get('first_principles', 0):
    print(f"    → Prefers ANALOGIES over FIRST PRINCIPLES for understanding")
else:
    print(f"    → Prefers FIRST PRINCIPLES over ANALOGIES for understanding")

if cat_counts.get('depth_seeking', 0) > cat_counts.get('cross_domain', 0):
    print(f"    → Tends toward DEPTH over BREADTH")
else:
    print(f"    → Tends toward BREADTH over DEPTH")

meta = cat_counts.get('meta_learning', 0)
print(f"    → Meta-learning awareness: {meta} instances ({meta/len(conv_files)*100:.1f}% of conversations)")

