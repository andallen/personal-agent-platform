#!/usr/bin/env python3
"""
Model comparison: Run extraction prompt on 10 conversations with both
Haiku 4.5 and Sonnet 4.6, save results side-by-side for quality review.

Usage: ANTHROPIC_API_KEY=sk-... python3 model_comparison.py
"""
import json
import os
import random
import sys
import time
import zipfile
from pathlib import Path

import httpx

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    print("Set ANTHROPIC_API_KEY environment variable")
    sys.exit(1)

EXPORTS_DIR = Path.home() / "ai-exports"
CONV_DIR = Path.home() / "tutor-extraction" / "conversations"
OUTPUT_DIR = Path.home() / "tutor-extraction" / "model_comparison_r2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPT_FILE = Path(__file__).parent / "extraction_prompt.txt"
SYSTEM_PROMPT = PROMPT_FILE.read_text()

MODELS = [
    ("claude-haiku-4-5-20251001", "haiku"),
    ("claude-sonnet-4-6", "sonnet"),
]


def extract_chatgpt_messages(conv):
    mapping = conv.get("mapping", {})
    nodes = []
    for node in mapping.values():
        msg = node.get("message")
        if msg is None:
            continue
        author = msg.get("author", {})
        role = author.get("role")
        if role not in ("user", "assistant"):
            continue
        parts = msg.get("content", {}).get("parts", [])
        text = " ".join(str(p) for p in parts if isinstance(p, str))
        if text.strip():
            ts = msg.get("create_time", 0) or 0
            nodes.append({"role": role, "text": text.strip(), "ts": ts})
    nodes.sort(key=lambda x: x["ts"])
    return [{"role": n["role"], "text": n["text"]} for n in nodes]


def extract_claude_messages(conv):
    messages = []
    for m in conv.get("chat_messages", []):
        role = "user" if m.get("sender") == "human" else "assistant"
        text = ""
        if isinstance(m.get("text"), str):
            text = m["text"]
        elif isinstance(m.get("content"), list):
            text = " ".join(
                p.get("text", "")
                for p in m["content"]
                if isinstance(p, dict) and "text" in p
            )
        elif isinstance(m.get("content"), str):
            text = m["content"]
        if text.strip():
            messages.append({"role": role, "text": text.strip()})
    return messages


def extract_cc_messages(jsonl_path):
    messages = []
    with open(jsonl_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            etype = entry.get("type")
            if etype not in ("user", "assistant"):
                continue
            if etype == "user" and entry.get("isMeta", False):
                continue
            content = entry.get("message", {}).get("content", "")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            else:
                continue
            if etype == "user":
                if text.startswith(("<command-name>", "/", "<local-command-stdout>")):
                    continue
            text = text.strip()
            if text:
                messages.append({"role": etype, "text": text})
    return messages


def format_conversation(conv_id, source, title, messages):
    lines = [f"CONVERSATION ID: {conv_id}"]
    lines.append(f"SOURCE: {source}")
    lines.append(f"TITLE: {title}")
    lines.append("")
    for m in messages:
        role_label = "HUMAN" if m["role"] == "user" else "AI"
        lines.append(f"[{role_label}]: {m['text']}")
        lines.append("")
    return "\n".join(lines)


def call_api(model_id, system, user_content, max_tokens=4096):
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model_id,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }
    for attempt in range(3):
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = "".join(
                    b["text"] for b in data["content"] if b["type"] == "text"
                )
                return text, data.get("usage", {})
            elif resp.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    API error {resp.status_code}: {resp.text[:200]}")
                if attempt < 2:
                    time.sleep(5)
        except Exception as e:
            print(f"    Request error: {e}")
            if attempt < 2:
                time.sleep(5)
    return None, None


def load_raw_conversations_by_title():
    """Build title→raw_data lookup from all exports."""
    by_title = {}

    # ChatGPT
    with zipfile.ZipFile(EXPORTS_DIR / "chatgpt_feb.zip") as z:
        for cf in sorted(f for f in z.namelist() if "conversations-" in f and f.endswith(".json")):
            with z.open(cf) as f:
                for c in json.load(f):
                    title = c.get("title") or "untitled"
                    by_title[("chatgpt", title)] = ("chatgpt", c)

    # Claude acc1, acc2
    for source in ["claude_acc1_feb", "claude_acc2_feb"]:
        with open(EXPORTS_DIR / source / "conversations.json") as f:
            for c in json.load(f):
                title = c.get("name") or "untitled"
                by_title[(source, title)] = (source, c)

    # Claude April
    with zipfile.ZipFile(EXPORTS_DIR / "claude_april.zip") as z:
        with z.open("conversations.json") as f:
            for c in json.load(f):
                title = c.get("name") or "untitled"
                by_title[("claude_april", title)] = ("claude_april", c)

    # Claude Code — key by folder name
    for sp in sorted((EXPORTS_DIR / "claude_code_april").rglob("*.jsonl")):
        title = sp.parent.name
        by_title[("claude_code", sp.stem)] = ("claude_code", sp)

    return by_title


EXCLUDE_IDS = {
    "5528e9faf228", "a1822535b75d", "8f30206853d4", "a7cb9d7751e4",
    "32d8d31a1682", "1645f4baa809", "6665b80e84ca", "5f1023e95a24",
}


def pick_10_conversations():
    """Pick 10 diverse preprocessed conversations by source and length."""
    convos = []
    for f in CONV_DIR.glob("*.json"):
        with open(f) as fh:
            d = json.load(fh)
        if d["id"] not in EXCLUDE_IDS and 3 <= d["metadata"]["num_messages"] <= 80:
            convos.append(d)

    sources = {}
    for c in convos:
        sources.setdefault(c["source"], []).append(c)

    random.seed(99)
    selected = []

    for source in ["chatgpt", "claude_april", "claude_acc2_feb", "claude_acc1_feb", "gemini"]:
        pool = sources.get(source, [])
        pool.sort(key=lambda c: c["metadata"]["total_chars"], reverse=True)
        top = pool[:max(5, len(pool) // 5)]
        random.shuffle(top)
        selected.extend(top[:2])

    return selected[:10]


def main():
    print("Picking 10 conversations...")
    selected = pick_10_conversations()
    for c in selected:
        print(f"  {c['id']} | {c['source']:15} | {c['metadata']['num_messages']:3} msgs | {c['title'][:55]}")

    print("\nLoading raw exports for full conversation text...")
    raw_lookup = load_raw_conversations_by_title()
    print(f"  Loaded {len(raw_lookup)} raw conversations")

    total_input_tokens = 0
    total_output_tokens = 0
    results = {}
    processed = 0

    for conv in selected:
        cid = conv["id"]
        source = conv["source"]
        title = conv["title"]

        # Find full conversation in raw exports
        raw_entry = raw_lookup.get((source, title))
        if raw_entry is None:
            # Try CC stem match
            for key, val in raw_lookup.items():
                if key[0] == source and title in key[1]:
                    raw_entry = val
                    break

        if raw_entry is None:
            print(f"\n  SKIP [{cid}] {title[:40]} — not found in raw exports")
            continue

        raw_source, raw_data = raw_entry
        if source == "chatgpt":
            messages = extract_chatgpt_messages(raw_data)
        elif source == "claude_code":
            messages = extract_cc_messages(raw_data)
        else:
            messages = extract_claude_messages(raw_data)

        if not messages:
            print(f"\n  SKIP [{cid}] {title[:40]} — no messages extracted")
            continue

        conv_text = format_conversation(cid, source, title, messages)
        est_tokens = len(conv_text) // 4

        print(f"\n{'='*70}")
        print(f"[{cid}] {title[:50]}")
        print(f"  Source: {source} | Full msgs: {len(messages)} | ~{est_tokens:,} tokens")
        print(f"{'='*70}")

        results[cid] = {
            "id": cid, "source": source, "title": title,
            "num_messages": len(messages), "est_input_tokens": est_tokens,
        }

        for model_id, model_name in MODELS:
            print(f"  Running {model_name}...", end=" ", flush=True)
            text, usage = call_api(model_id, SYSTEM_PROMPT, conv_text)
            if text:
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                total_input_tokens += in_tok
                total_output_tokens += out_tok
                print(f"done ({in_tok:,} in / {out_tok:,} out)")
                results[cid][model_name] = {"output": text, "usage": usage}
                (OUTPUT_DIR / f"{cid}_{model_name}.txt").write_text(text)
            else:
                print("FAILED")
                results[cid][model_name] = None

        processed += 1

    # Save summary
    with open(OUTPUT_DIR / "comparison_summary.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*70}")
    print("COMPARISON COMPLETE")
    print(f"{'='*70}")
    print(f"  Conversations processed: {processed}")
    print(f"  Results saved to: {OUTPUT_DIR}")
    print(f"  Total input tokens:  {total_input_tokens:,}")
    print(f"  Total output tokens: {total_output_tokens:,}")

    def safe_sum(model_name, field):
        total = 0
        for r in results.values():
            m = r.get(model_name)
            if m and m.get("usage"):
                total += m["usage"].get(field, 0)
        return total

    haiku_in = safe_sum("haiku", "input_tokens")
    haiku_out = safe_sum("haiku", "output_tokens")
    sonnet_in = safe_sum("sonnet", "input_tokens")
    sonnet_out = safe_sum("sonnet", "output_tokens")

    haiku_cost = haiku_in * 1.0 / 1e6 + haiku_out * 5.0 / 1e6
    sonnet_cost = sonnet_in * 3.0 / 1e6 + sonnet_out * 15.0 / 1e6

    print(f"\n  Haiku cost  (this run): ${haiku_cost:.4f}")
    print(f"  Sonnet cost (this run): ${sonnet_cost:.4f}")
    print(f"  Total:                  ${haiku_cost + sonnet_cost:.4f}")

    n_haiku = max(1, len([r for r in results.values() if r.get("haiku")]))
    n_sonnet = max(1, len([r for r in results.values() if r.get("sonnet")]))

    avg_in_h = haiku_in / n_haiku
    avg_in_s = sonnet_in / n_sonnet
    avg_out_h = haiku_out / n_haiku
    avg_out_s = sonnet_out / n_sonnet

    n = 3002
    print(f"\n  Extrapolated full-corpus cost (batch pricing, 50% discount):")
    print(f"    All Haiku:  ${n * avg_in_h * 0.5/1e6 + n * avg_out_h * 2.5/1e6:.2f}")
    print(f"    All Sonnet: ${n * avg_in_s * 1.5/1e6 + n * avg_out_s * 7.5/1e6:.2f}")


if __name__ == "__main__":
    main()
