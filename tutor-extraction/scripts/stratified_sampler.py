"""
Stratified sampler for learning-pattern codebook discovery.

Selects 200 conversations from ~5,370 to maximally represent the diversity
of the corpus across source, length, domain, learning-signal score, and time.

Design rationale
----------------
A pattern codebook must capture the FULL vocabulary of learning behaviors,
including rare ones. Common patterns surface in any reasonable sample; rare
patterns require deliberate oversampling of underrepresented strata.

The algorithm works in four phases:

  Phase 1 — Mandatory slots (~25-40 conversations)
      Hard constraints: top-scored picks, low-score calibration picks,
      source-minimum guarantees. These are non-negotiable.

  Phase 2 — Stratified grid (~120 conversations)
      Cross source x length x domain x score-quartile to form cells.
      Allocate slots to cells using cube-root weighting (dampens the
      dominance of large cells while still respecting corpus shape).
      Within each cell, pick conversations at evenly-spaced score
      quantiles for maximum internal spread.

  Phase 3 — Temporal coverage check (~10-20 conversations)
      Divide the Dec-2022-to-Apr-2026 span into 8 quarter-year windows.
      Any window with fewer than 3 representatives gets backfilled.

  Phase 4 — Diversity fill (remaining slots)
      Greedily pick conversations that maximize the minimum distance to
      any already-selected conversation in a normalized feature space.
      This is a max-min diversity algorithm that fills gaps.

Multi-label domain handling: conversations can carry multiple domain tags.
For stratification, each conversation is assigned to its LEAST frequent
matching domain. This naturally oversamples rare domains — exactly what
codebook discovery needs.

Usage
-----
    from stratified_sampler import select_stratified_sample
    indices = select_stratified_sample(conversations, n=200)
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LENGTH_BINS = {
    "short": (2, 5),
    "medium": (6, 20),
    "long": (21, float("inf")),
}

DOMAINS = ["cs", "math", "finance", "philosophy", "personal_dev", "other", "none"]

SCORE_QUARTILE_EDGES = [0.0, 0.155, 0.267, 0.431, 1.0]  # P0, P25, P50, P75, P100
SCORE_QUARTILE_LABELS = ["Q1_low", "Q2_mid_low", "Q3_mid_high", "Q4_high"]

# Minimum conversations per temporal window before backfill kicks in.
TEMPORAL_MIN_PER_WINDOW = 3
TEMPORAL_WINDOWS = 8  # ~5-month windows across Dec 2022 - Apr 2026

# Oversampling multipliers for length bins (applied during allocation).
# "long" gets 2x weight, "short" gets 0.7x — we want rare long conversations.
LENGTH_WEIGHT = {"short": 0.7, "medium": 1.0, "long": 2.0}

# Oversampling multipliers for score quartiles.
# Q4 (high signal) gets 1.8x; Q1 (low) gets 0.6x but is partly covered
# by the mandatory calibration picks anyway.
SCORE_WEIGHT = {"Q1_low": 0.6, "Q2_mid_low": 0.9, "Q3_mid_high": 1.2, "Q4_high": 1.8}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_length(num_messages: int) -> str:
    for label, (lo, hi) in LENGTH_BINS.items():
        if lo <= num_messages <= hi:
            return label
    return "short"  # fallback for edge cases like 0 or 1 messages


def _classify_score_quartile(score: float) -> str:
    for i in range(len(SCORE_QUARTILE_LABELS)):
        if score <= SCORE_QUARTILE_EDGES[i + 1]:
            return SCORE_QUARTILE_LABELS[i]
    return SCORE_QUARTILE_LABELS[-1]


def _assign_primary_domain(domain_tags: list[str], domain_freq: dict[str, int]) -> str:
    """Assign conversation to its LEAST frequent domain tag.

    This ensures rare domains get more representatives — critical for
    discovering uncommon learning patterns (e.g., philosophy-style
    Socratic questioning is rare at 14% but may hold unique patterns).
    """
    if not domain_tags:
        return "none"
    # Normalize tags to lowercase and filter to known domains.
    normalized = []
    for tag in domain_tags:
        t = tag.lower().replace(" ", "_").replace("-", "_")
        # Map common variants.
        if t in ("computer_science", "cs", "programming", "coding"):
            t = "cs"
        elif t in ("mathematics", "math", "stats", "statistics"):
            t = "math"
        elif t in ("finance", "economics", "investing"):
            t = "finance"
        elif t in ("philosophy", "ethics", "logic_philosophy"):
            t = "philosophy"
        elif t in ("personal_dev", "personal_development", "self_improvement", "productivity"):
            t = "personal_dev"
        else:
            t = "other"
        normalized.append(t)
    if not normalized:
        return "none"
    # Pick the least frequent domain among the conversation's tags.
    return min(normalized, key=lambda d: domain_freq.get(d, 0))


def _timestamp_to_float(ts) -> float:
    """Convert timestamp to a float (seconds since epoch) for math."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        # Try ISO format first, then common variants.
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(ts, fmt).timestamp()
            except ValueError:
                continue
        # Last resort: strip timezone info and retry.
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    if isinstance(ts, datetime):
        return ts.timestamp()
    return 0.0


def _temporal_window(ts_float: float, t_min: float, t_max: float, n_windows: int) -> int:
    """Map a timestamp float to a window index in [0, n_windows-1]."""
    if t_max == t_min:
        return 0
    frac = (ts_float - t_min) / (t_max - t_min)
    frac = max(0.0, min(frac, 1.0 - 1e-12))
    return int(frac * n_windows)


def _normalized_feature_vector(conv: dict, domain_freq: dict[str, int],
                                t_min: float, t_max: float) -> list[float]:
    """Build a simple normalized feature vector for diversity distance calc.

    Features (all in [0,1]):
      0: source encoded (categorical -> ordinal, not ideal but workable)
      1: length bin (0, 0.5, 1)
      2: score (raw, already roughly 0-1)
      3: temporal position
      4-10: domain one-hot (7 domains)
    """
    sources = {"chatgpt": 0.0, "claude": 0.33, "gemini": 0.67}
    src_val = sources.get(conv.get("source", "").lower().split("_")[0], 0.5)

    length_vals = {"short": 0.0, "medium": 0.5, "long": 1.0}
    len_val = length_vals.get(_classify_length(conv.get("num_messages", 0)), 0.5)

    score_val = min(max(conv.get("score", 0.0), 0.0), 1.0)

    ts = _timestamp_to_float(conv.get("timestamp", 0))
    t_range = t_max - t_min if t_max > t_min else 1.0
    time_val = (ts - t_min) / t_range

    primary = _assign_primary_domain(conv.get("domain_tags", []), domain_freq)
    domain_vec = [1.0 if d == primary else 0.0 for d in DOMAINS]

    return [src_val, len_val, score_val, time_val] + domain_vec


def _distance_sq(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Main sampling function
# ---------------------------------------------------------------------------


def select_stratified_sample(
    conversations: list[dict[str, Any]],
    n: int = 200,
    seed: int = 42,
    verbose: bool = False,
) -> list[int]:
    """Select n conversations that maximally represent corpus diversity.

    Parameters
    ----------
    conversations : list[dict]
        Each dict must have keys:
          - source: str          (e.g. "chatgpt", "claude", "gemini")
          - num_messages: int    (total messages in the conversation)
          - domain_tags: list[str]  (detected domains, may be empty)
          - score: float         (composite learning-signal score, 0-1 range)
          - timestamp: str|float|datetime  (when the conversation occurred)
    n : int
        Target sample size (default 200).
    seed : int
        Random seed for reproducibility within tie-breaking steps.

    Returns
    -------
    list[int]
        Indices into `conversations` of the selected sample.

    Raises
    ------
    ValueError
        If the corpus is smaller than n or constraints cannot be satisfied.
    """
    rng = random.Random(seed)

    if len(conversations) < n:
        raise ValueError(
            f"Corpus has {len(conversations)} conversations but n={n} requested."
        )

    # ------------------------------------------------------------------
    # Pre-compute per-conversation metadata
    # ------------------------------------------------------------------

    # Domain frequency across the whole corpus (for least-frequent assignment).
    domain_counter: Counter = Counter()
    for conv in conversations:
        tags = conv.get("domain_tags", [])
        if not tags:
            domain_counter["none"] += 1
        for tag in tags:
            t = tag.lower().replace(" ", "_").replace("-", "_")
            if t in ("computer_science", "cs", "programming", "coding"):
                domain_counter["cs"] += 1
            elif t in ("mathematics", "math", "stats", "statistics"):
                domain_counter["math"] += 1
            elif t in ("finance", "economics", "investing"):
                domain_counter["finance"] += 1
            elif t in ("philosophy", "ethics", "logic_philosophy"):
                domain_counter["philosophy"] += 1
            elif t in ("personal_dev", "personal_development", "self_improvement", "productivity"):
                domain_counter["personal_dev"] += 1
            else:
                domain_counter["other"] += 1
    domain_freq = dict(domain_counter)

    meta = []
    for i, conv in enumerate(conversations):
        meta.append({
            "idx": i,
            "source": conv.get("source", "unknown").lower(),
            "length_bin": _classify_length(conv.get("num_messages", 0)),
            "primary_domain": _assign_primary_domain(conv.get("domain_tags", []), domain_freq),
            "score_q": _classify_score_quartile(conv.get("score", 0.0)),
            "score": conv.get("score", 0.0),
            "ts_float": _timestamp_to_float(conv.get("timestamp", 0)),
        })

    ts_values = [m["ts_float"] for m in meta if m["ts_float"] > 0]
    t_min = min(ts_values) if ts_values else 0.0
    t_max = max(ts_values) if ts_values else 1.0

    for m in meta:
        m["temporal_window"] = _temporal_window(m["ts_float"], t_min, t_max, TEMPORAL_WINDOWS)

    selected: set[int] = set()

    def _add(idx: int):
        selected.add(idx)

    def _is_available(idx: int) -> bool:
        return idx not in selected

    # ------------------------------------------------------------------
    # Phase 1: Mandatory picks
    # ------------------------------------------------------------------

    # 1a. Top-30 by score — pick at least 10.
    sorted_by_score = sorted(range(len(conversations)), key=lambda i: -meta[i]["score"])
    top30 = sorted_by_score[:30]

    # Pick the top 10 outright (highest signal, most pattern-rich).
    for idx in top30[:10]:
        _add(idx)

    # 1b. Calibration: at least 15 with score < P25 (0.155).
    # Spread across different sources/domains to ensure calibration variety.
    calibration_pool = [
        m["idx"] for m in meta
        if m["score"] < SCORE_QUARTILE_EDGES[1] and _is_available(m["idx"])
    ]
    # Sort by diversity: group by (source, primary_domain) and round-robin.
    cal_by_group: dict[tuple, list[int]] = defaultdict(list)
    for idx in calibration_pool:
        key = (meta[idx]["source"], meta[idx]["primary_domain"])
        cal_by_group[key].append(idx)
    # Within each group, sort by score ascending (pick the lowest first).
    for key in cal_by_group:
        cal_by_group[key].sort(key=lambda i: meta[i]["score"])
    # Round-robin across groups.
    cal_picked = 0
    cal_target = 15
    group_keys = sorted(cal_by_group.keys())
    rng.shuffle(group_keys)
    round_idx = 0
    while cal_picked < cal_target and group_keys:
        key = group_keys[round_idx % len(group_keys)]
        while cal_by_group[key] and not _is_available(cal_by_group[key][0]):
            cal_by_group[key].pop(0)
        if cal_by_group[key]:
            _add(cal_by_group[key].pop(0))
            cal_picked += 1
        else:
            group_keys.remove(key)
            if not group_keys:
                break
            round_idx = round_idx % len(group_keys) if group_keys else 0
            continue
        round_idx += 1

    # 1c. Source minimums: at least 5 from each source.
    source_counts: Counter = Counter()
    for idx in selected:
        source_counts[meta[idx]["source"]] += 1

    all_sources = set(m["source"] for m in meta)
    for source in all_sources:
        deficit = 5 - source_counts.get(source, 0)
        if deficit > 0:
            # Pick highest-scored available from this source.
            pool = [
                m["idx"] for m in meta
                if m["source"] == source and _is_available(m["idx"])
            ]
            pool.sort(key=lambda i: -meta[i]["score"])
            for idx in pool[:deficit]:
                _add(idx)
                source_counts[source] = source_counts.get(source, 0) + 1

    if verbose:
        print(f"Phase 1 complete: {len(selected)} mandatory picks")

    # ------------------------------------------------------------------
    # Phase 2: Stratified grid allocation
    # ------------------------------------------------------------------

    sources_in_corpus = sorted(all_sources)
    length_bins = list(LENGTH_BINS.keys())
    domains = DOMAINS
    score_qs = SCORE_QUARTILE_LABELS

    # Build cell membership: cell_key -> list of conversation indices.
    cells: dict[tuple, list[int]] = defaultdict(list)
    for m in meta:
        cell_key = (m["source"], m["length_bin"], m["primary_domain"], m["score_q"])
        cells[cell_key].append(m["idx"])

    # Compute allocation per cell using cube-root weighting with oversampling.
    phase2_budget = n - len(selected) - 20  # reserve ~20 for phases 3-4
    phase2_budget = max(phase2_budget, 80)  # ensure reasonable grid coverage

    raw_weights = {}
    for key, members in cells.items():
        source, length_bin, domain, score_q = key
        base = len(members) ** (1.0 / 3.0)  # cube root dampens large cells
        weight = base * LENGTH_WEIGHT.get(length_bin, 1.0) * SCORE_WEIGHT.get(score_q, 1.0)
        # Extra boost for rare domains.
        if domain in ("philosophy", "other", "none"):
            weight *= 1.3
        raw_weights[key] = weight

    # Filter to non-empty cells only.
    nonempty_keys = [k for k in cells if cells[k]]
    total_weight = sum(raw_weights[k] for k in nonempty_keys)
    if total_weight == 0:
        total_weight = 1.0

    # Fractional allocation (no floor yet).
    frac_alloc = {
        key: phase2_budget * raw_weights[key] / total_weight
        for key in nonempty_keys
    }

    # Use largest-remainder method to get integer allocations that sum
    # exactly to phase2_budget. No per-cell minimum — cells that round
    # to 0 will be covered by the Phase 4 diversity fill.
    int_alloc = {key: int(frac_alloc[key]) for key in nonempty_keys}
    remainders = {key: frac_alloc[key] - int_alloc[key] for key in nonempty_keys}
    shortfall = phase2_budget - sum(int_alloc.values())
    # Award the remaining slots to cells with the largest fractional parts.
    for key in sorted(remainders, key=remainders.get, reverse=True):  # type: ignore[arg-type]
        if shortfall <= 0:
            break
        int_alloc[key] += 1
        shortfall -= 1

    allocations = int_alloc

    # Within each cell, pick at evenly-spaced score quantiles.
    for key, target_count in allocations.items():
        if target_count <= 0:
            continue
        available = [i for i in cells[key] if _is_available(i)]
        if not available:
            continue
        # Sort by score for quantile-spaced picking.
        available.sort(key=lambda i: meta[i]["score"])
        pick_count = min(target_count, len(available))
        if pick_count >= len(available):
            # Take all.
            for idx in available:
                _add(idx)
        else:
            # Pick at evenly spaced positions (quantile sampling).
            step = len(available) / pick_count
            for j in range(pick_count):
                pos = int(j * step + step / 2)
                pos = min(pos, len(available) - 1)
                _add(available[pos])

    if verbose:
        print(f"Phase 2 complete: {len(selected)} total after grid allocation")

    # ------------------------------------------------------------------
    # Phase 3: Temporal backfill
    # ------------------------------------------------------------------

    window_counts: Counter = Counter()
    for idx in selected:
        window_counts[meta[idx]["temporal_window"]] += 1

    phase3_budget = min(20, n - len(selected))
    phase3_picks = 0

    for w in range(TEMPORAL_WINDOWS):
        deficit = TEMPORAL_MIN_PER_WINDOW - window_counts.get(w, 0)
        if deficit > 0 and phase3_picks < phase3_budget:
            pool = [
                m["idx"] for m in meta
                if m["temporal_window"] == w and _is_available(m["idx"])
            ]
            # Prefer high-score within the window.
            pool.sort(key=lambda i: -meta[i]["score"])
            for idx in pool[: min(deficit, phase3_budget - phase3_picks)]:
                _add(idx)
                phase3_picks += 1

    if verbose:
        print(f"Phase 3 complete: {len(selected)} total after temporal backfill")

    # ------------------------------------------------------------------
    # Phase 4: Max-min diversity fill
    # ------------------------------------------------------------------

    remaining = n - len(selected)
    if remaining > 0:
        # Pre-compute feature vectors.
        fvecs = {
            i: _normalized_feature_vector(conversations[i], domain_freq, t_min, t_max)
            for i in range(len(conversations))
        }

        # For each available candidate, track min distance to selected set.
        available_indices = [i for i in range(len(conversations)) if _is_available(i)]

        # Initialize min-distances.
        min_dists: dict[int, float] = {}
        selected_list = list(selected)
        for i in available_indices:
            min_d = float("inf")
            for s in selected_list:
                d = _distance_sq(fvecs[i], fvecs[s])
                if d < min_d:
                    min_d = d
            min_dists[i] = min_d

        for _ in range(remaining):
            if not min_dists:
                break
            # Pick the candidate with the largest min-distance (most different).
            best = max(min_dists, key=min_dists.__getitem__) # type: ignore[arg-type]
            _add(best)
            best_fv = fvecs[best]
            del min_dists[best]
            # Update remaining candidates' min-distances.
            for i in list(min_dists.keys()):
                d = _distance_sq(fvecs[i], best_fv)
                if d < min_dists[i]:
                    min_dists[i] = d

    if verbose:
        print(f"Phase 4 complete: {len(selected)} total after diversity fill")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    result = sorted(selected)
    assert len(result) == n, f"Expected {n}, got {len(result)}"

    # Check constraints.
    top30_in_sample = len(set(top30) & selected)
    assert top30_in_sample >= 10, (
        f"Only {top30_in_sample} of top-30 in sample (need >= 10)"
    )

    cal_in_sample = sum(1 for i in result if meta[i]["score"] < SCORE_QUARTILE_EDGES[1])
    assert cal_in_sample >= 15, (
        f"Only {cal_in_sample} calibration conversations (need >= 15)"
    )

    source_check: Counter = Counter()
    for i in result:
        source_check[meta[i]["source"]] += 1
    for source in all_sources:
        assert source_check.get(source, 0) >= 5, (
            f"Source '{source}' has only {source_check.get(source, 0)} (need >= 5)"
        )

    return result


# ---------------------------------------------------------------------------
# Diagnostics: print a breakdown of the selected sample
# ---------------------------------------------------------------------------


def describe_sample(conversations: list[dict], indices: list[int]) -> None:
    """Print a human-readable breakdown of the selected sample."""
    from collections import Counter

    sample = [conversations[i] for i in indices]

    print(f"\n{'='*60}")
    print(f"SAMPLE SUMMARY: {len(indices)} conversations selected")
    print(f"{'='*60}")

    # Source distribution.
    source_c = Counter(c.get("source", "unknown").lower() for c in sample)
    corpus_source_c = Counter(c.get("source", "unknown").lower() for c in conversations)
    print(f"\n--- Source distribution ---")
    print(f"  {'Source':<12} {'Sample':>7} {'Corpus':>7} {'Sample%':>8} {'Corpus%':>8}")
    for src in sorted(set(list(source_c.keys()) + list(corpus_source_c.keys()))):
        s_n = source_c.get(src, 0)
        c_n = corpus_source_c.get(src, 0)
        s_pct = 100 * s_n / len(sample) if sample else 0
        c_pct = 100 * c_n / len(conversations) if conversations else 0
        print(f"  {src:<12} {s_n:>7} {c_n:>7} {s_pct:>7.1f}% {c_pct:>7.1f}%")

    # Length distribution.
    len_c = Counter(_classify_length(c.get("num_messages", 0)) for c in sample)
    corpus_len_c = Counter(_classify_length(c.get("num_messages", 0)) for c in conversations)
    print(f"\n--- Length distribution ---")
    print(f"  {'Bin':<10} {'Sample':>7} {'Corpus':>7} {'Sample%':>8} {'Corpus%':>8}")
    for b in ["short", "medium", "long"]:
        s_n = len_c.get(b, 0)
        c_n = corpus_len_c.get(b, 0)
        s_pct = 100 * s_n / len(sample) if sample else 0
        c_pct = 100 * c_n / len(conversations) if conversations else 0
        print(f"  {b:<10} {s_n:>7} {c_n:>7} {s_pct:>7.1f}% {c_pct:>7.1f}%")

    # Score distribution.
    scores = sorted(c.get("score", 0) for c in sample)
    print(f"\n--- Score distribution (sample) ---")
    for pct in [10, 25, 50, 75, 90]:
        idx = int(len(scores) * pct / 100)
        idx = min(idx, len(scores) - 1)
        print(f"  P{pct:>2}: {scores[idx]:.3f}")

    # Domain distribution.
    domain_freq = Counter()
    for c in conversations:
        for t in c.get("domain_tags", []):
            domain_freq[t.lower()] += 1
    if not domain_freq:
        domain_freq["none"] = len(conversations)

    domain_c = Counter()
    for c in sample:
        pd = _assign_primary_domain(c.get("domain_tags", []), dict(domain_freq))
        domain_c[pd] += 1
    print(f"\n--- Primary domain distribution (sample) ---")
    for d in DOMAINS:
        print(f"  {d:<15} {domain_c.get(d, 0):>5}  ({100*domain_c.get(d, 0)/len(sample):>5.1f}%)")

    # Temporal spread.
    ts_vals = [_timestamp_to_float(c.get("timestamp", 0)) for c in sample]
    ts_vals = [t for t in ts_vals if t > 0]
    if ts_vals:
        earliest = datetime.fromtimestamp(min(ts_vals)).strftime("%Y-%m-%d")
        latest = datetime.fromtimestamp(max(ts_vals)).strftime("%Y-%m-%d")
        print(f"\n--- Temporal range ---")
        print(f"  Earliest: {earliest}")
        print(f"  Latest:   {latest}")

        all_ts = [_timestamp_to_float(c.get("timestamp", 0)) for c in conversations]
        all_ts = [t for t in all_ts if t > 0]
        t_min_all = min(all_ts)
        t_max_all = max(all_ts)
        print(f"\n--- Temporal window coverage ---")
        window_c = Counter()
        for t in ts_vals:
            w = _temporal_window(t, t_min_all, t_max_all, TEMPORAL_WINDOWS)
            window_c[w] += 1
        for w in range(TEMPORAL_WINDOWS):
            bar = "#" * window_c.get(w, 0)
            print(f"  Window {w}: {window_c.get(w, 0):>3}  {bar}")

    print(f"\n{'='*60}\n")


# ---------------------------------------------------------------------------
# Demo / test with synthetic data
# ---------------------------------------------------------------------------


def _generate_synthetic_corpus(n: int = 5370, seed: int = 42) -> list[dict]:
    """Generate a synthetic corpus that mirrors the described real distribution."""
    rng = random.Random(seed)

    # Source proportions (rough estimate from 4 exports: ChatGPT, Claude x3, Gemini).
    sources = ["chatgpt", "claude", "gemini"]
    source_weights = [0.35, 0.45, 0.20]  # Claude has 3 accounts so more volume

    # Domain keyword detection rates (multi-label, so they sum > 100%).
    domain_probs = {
        "cs": 0.43,
        "math": 0.37,
        "personal_dev": 0.37,
        "finance": 0.34,
        "philosophy": 0.14,
    }

    # Score distribution: log-normal-ish to match P25=0.155, P50=0.267, P75=0.431.
    # A log-normal with mu=-1.3, sigma=0.75 roughly fits.
    import math as _math

    corpus = []
    # Temporal range: Dec 2022 to Apr 2026 (in epoch seconds).
    t_start = datetime(2022, 12, 1).timestamp()
    t_end = datetime(2026, 4, 28).timestamp()

    for _ in range(n):
        # Source.
        r = rng.random()
        cum = 0
        src = sources[-1]
        for s, w in zip(sources, source_weights):
            cum += w
            if r < cum:
                src = s
                break

        # Message count: heavy-tailed. Most are short/medium.
        msg_count = max(2, int(rng.lognormvariate(2.0, 0.9)))
        msg_count = min(msg_count, 200)

        # Domains (multi-label).
        tags = []
        for domain, prob in domain_probs.items():
            if rng.random() < prob:
                tags.append(domain)

        # Score: log-normal.
        raw_score = rng.lognormvariate(-1.3, 0.75)
        score = min(max(raw_score, 0.0), 1.0)
        # Longer conversations tend to have higher scores.
        if msg_count > 20:
            score = min(score * 1.3, 1.0)

        # Timestamp: roughly uniform with slight acceleration over time.
        t_frac = rng.betavariate(2, 3)  # slight skew toward earlier
        ts = t_start + t_frac * (t_end - t_start)

        corpus.append({
            "source": src,
            "num_messages": msg_count,
            "domain_tags": tags,
            "score": round(score, 4),
            "timestamp": datetime.fromtimestamp(ts).isoformat(),
        })

    return corpus


def _run_demo():
    """Run the sampler on synthetic data and display diagnostics."""
    print("Generating synthetic corpus of ~5,370 conversations...")
    corpus = _generate_synthetic_corpus(5370)

    # Quick corpus stats.
    scores = sorted(c["score"] for c in corpus)
    print(f"Corpus score quantiles:")
    for pct in [25, 50, 75, 90]:
        idx = int(len(scores) * pct / 100)
        print(f"  P{pct}: {scores[idx]:.3f}")

    print(f"\nRunning stratified sampler...")
    indices = select_stratified_sample(corpus, n=200, verbose=True)

    print(f"\nSelected {len(indices)} conversations.")
    describe_sample(corpus, indices)

    # Verify all constraints hold.
    print("All constraints satisfied. Sample is ready for codebook development.")


if __name__ == "__main__":
    _run_demo()
