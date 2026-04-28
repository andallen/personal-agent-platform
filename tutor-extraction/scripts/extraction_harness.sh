#!/usr/bin/env bash
#
# extraction_harness.sh -- Batch learning-pattern extraction via claude -p
#
# Processes a directory of preprocessed conversation JSON files through
# Claude Code CLI in non-interactive mode, extracting structured learning
# patterns from each conversation.
#
# USAGE:
#   ./extraction_harness.sh -i INPUT_DIR -o OUTPUT_DIR [OPTIONS]
#
# REQUIRED:
#   -i INPUT_DIR    Directory containing conversation JSON files.
#                   Each file: {id, source, title, user_messages, metadata}
#   -o OUTPUT_DIR   Directory for output JSON files ({id}.json each)
#
# OPTIONS:
#   -p PROMPT_FILE  Path to extraction prompt template
#                   (default: ./extraction_prompt.txt)
#   -d DELAY        Seconds between calls (default: 3)
#   -r RPM          Max requests per minute (default: 40)
#   -b BATCH_SIZE   Conversations per claude call (default: 1; max ~5)
#   -m MODEL        Model to use (default: sonnet)
#   -j PROGRESS     Path to progress JSON file
#                   (default: OUTPUT_DIR/progress.json)
#   -n              Dry run -- show what would be processed, no API calls
#   -v              Verbose logging to stderr
#   -h              Show this help
#
# INPUT FILE FORMAT (one per conversation):
#   {
#     "id": "conv_abc123",
#     "source": "chatgpt",
#     "title": "Understanding Transformers",
#     "user_messages": ["msg1", "msg2", ...],
#     "metadata": {
#       "num_messages": 14,
#       "score": 0.82,
#       "domain_tags": ["ml", "nlp"]
#     }
#   }
#
# OUTPUT FILE FORMAT (one per conversation, in OUTPUT_DIR):
#   {id}.json containing the structured extraction result.
#
# RESUME: If an output file already exists for a conversation id,
#         that conversation is skipped automatically.
#
# SIGNALS: SIGINT/SIGTERM trigger a clean shutdown -- the current call
#          finishes, progress is saved, and the script exits cleanly.
#          Run again with the same arguments to resume.
#
# EXAMPLES:
#   # Basic single-file-at-a-time processing
#   ./extraction_harness.sh -i ./conversations -o ./extractions
#
#   # Batch 5 at a time, use opus, verbose
#   ./extraction_harness.sh -i ./conversations -o ./extractions -b 5 -m opus -v
#
#   # Dry run to see what would be processed
#   ./extraction_harness.sh -i ./conversations -o ./extractions -n

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────
PROMPT_FILE="./extraction_prompt.txt"
DELAY=3
RPM_LIMIT=40
BATCH_SIZE=1
MODEL="sonnet"
DRY_RUN=false
VERBOSE=false
PROGRESS_FILE=""
INPUT_DIR=""
OUTPUT_DIR=""

# ── Runtime state ─────────────────────────────────────────────────────
SHUTDOWN_REQUESTED=false
COMPLETED=0
FAILED=0
SKIPPED=0
TOTAL=0
START_EPOCH=0

# Sliding window for RPM tracking: timestamps of recent calls
declare -a CALL_TIMESTAMPS=()

# ── Functions ─────────────────────────────────────────────────────────

usage() {
    sed -n '2,/^[^#]/{ /^#/s/^# \?//p }' "$0"
    exit 0
}

log() {
    echo "[$(date '+%H:%M:%S')] $*" >&2
}

vlog() {
    [[ "$VERBOSE" == true ]] && log "$@"
    return 0
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

# ── Signal handling ───────────────────────────────────────────────────

cleanup() {
    SHUTDOWN_REQUESTED=true
    log "Shutdown requested -- finishing current work..."
}

trap cleanup SIGINT SIGTERM

save_progress() {
    local elapsed=$(( $(date +%s) - START_EPOCH ))
    cat > "$PROGRESS_FILE" <<PEOF
{
  "completed": $COMPLETED,
  "failed": $FAILED,
  "skipped": $SKIPPED,
  "total": $TOTAL,
  "elapsed_seconds": $elapsed,
  "last_updated": "$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
}
PEOF
    vlog "Progress saved to $PROGRESS_FILE"
}

# ── Rate limiting ─────────────────────────────────────────────────────

prune_old_timestamps() {
    local now
    now=$(date +%s)
    local cutoff=$(( now - 60 ))
    local new_ts=()
    for ts in "${CALL_TIMESTAMPS[@]}"; do
        if (( ts > cutoff )); then
            new_ts+=("$ts")
        fi
    done
    CALL_TIMESTAMPS=("${new_ts[@]+"${new_ts[@]}"}")
}

rpm_wait() {
    # Block until we are under RPM_LIMIT calls in the last 60 seconds
    while true; do
        prune_old_timestamps
        local count=${#CALL_TIMESTAMPS[@]}
        if (( count < RPM_LIMIT )); then
            break
        fi
        vlog "RPM limit ($RPM_LIMIT) reached ($count calls in window) -- waiting 5s"
        sleep 5
        if [[ "$SHUTDOWN_REQUESTED" == true ]]; then return 1; fi
    done
    return 0
}

record_call() {
    CALL_TIMESTAMPS+=("$(date +%s)")
}

# ── Core: invoke claude -p ────────────────────────────────────────────

run_claude() {
    # $1 = full prompt text
    # Returns: stdout = claude's JSON output, return code = success/failure
    local prompt="$1"

    local -a cmd=(
        claude
        -p
        --output-format json
        --bare
        --model "$MODEL"
    )

    # claude -p reads the prompt from the positional argument
    "${cmd[@]}" "$prompt" 2>/dev/null
}

call_with_backoff() {
    # $1 = prompt
    # Tries the call with exponential backoff: 5s, 10s, 20s, 40s
    local prompt="$1"
    local backoffs=(5 10 20 40)
    local attempt=0

    while true; do
        local raw_output
        if raw_output=$(run_claude "$prompt"); then
            # claude --output-format json wraps the result in a JSON envelope.
            # Extract the assistant's text content from the result field.
            local extracted
            extracted=$(echo "$raw_output" | python3 -c '
import sys, json
data = json.load(sys.stdin)
# --output-format json returns {"type":"result","result":"<text>",...}
text = data.get("result", "")
# The model may wrap JSON in markdown fences; strip them.
text = text.strip()
if text.startswith("```"):
    lines = text.split("\n")
    # Remove first line (```json or ```) and last line (```)
    if lines[-1].strip() == "```":
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    text = "\n".join(lines)
print(text)
' 2>/dev/null)

            # Validate that extracted content is parseable JSON
            if echo "$extracted" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
                echo "$extracted"
                return 0
            else
                vlog "Response was not valid JSON, treating as failure"
                vlog "Raw first 200 chars: ${extracted:0:200}"
            fi
        fi

        if (( attempt >= ${#backoffs[@]} )); then
            return 1
        fi

        local wait=${backoffs[$attempt]}
        log "Call failed (attempt $((attempt+1))) -- backing off ${wait}s"
        sleep "$wait"
        if [[ "$SHUTDOWN_REQUESTED" == true ]]; then return 1; fi
        (( attempt++ )) || true
    done
}

# ── Build prompt for single conversation ──────────────────────────────

build_single_prompt() {
    # $1 = path to conversation JSON file
    # $2 = extraction prompt template text
    local conv_file="$1"
    local template="$2"

    python3 -c '
import sys, json

template = sys.argv[1]
with open(sys.argv[2]) as f:
    conv = json.load(f)

conv_id = conv["id"]
title = conv.get("title", "(untitled)")
messages = conv.get("user_messages", [])

prompt_parts = [template, "", "---", ""]
prompt_parts.append(f"CONVERSATION ID: {conv_id}")
prompt_parts.append(f"TITLE: {title}")
prompt_parts.append(f"USER MESSAGES ({len(messages)} total):")
prompt_parts.append("")
for i, msg in enumerate(messages, 1):
    prompt_parts.append(f"[Message {i}]")
    prompt_parts.append(msg)
    prompt_parts.append("")

print("\n".join(prompt_parts))
' "$template" "$conv_file"
}

# ── Build prompt for batch of conversations ───────────────────────────

build_batch_prompt() {
    # $1 = extraction prompt template text
    # Remaining args = paths to conversation JSON files
    local template="$1"
    shift
    local files=("$@")

    python3 -c '
import sys, json

template = sys.argv[1]
files = sys.argv[2:]

prompt_parts = [template, "", "---", ""]
prompt_parts.append(f"BATCH OF {len(files)} CONVERSATIONS. Return a JSON array with one result object per conversation, in the same order.")
prompt_parts.append("")

for idx, fpath in enumerate(files, 1):
    with open(fpath) as f:
        conv = json.load(f)
    conv_id = conv["id"]
    title = conv.get("title", "(untitled)")
    messages = conv.get("user_messages", [])

    prompt_parts.append(f"=== CONVERSATION {idx} ===")
    prompt_parts.append(f"CONVERSATION ID: {conv_id}")
    prompt_parts.append(f"TITLE: {title}")
    prompt_parts.append(f"USER MESSAGES ({len(messages)} total):")
    prompt_parts.append("")
    for i, msg in enumerate(messages, 1):
        prompt_parts.append(f"[Message {i}]")
        prompt_parts.append(msg)
        prompt_parts.append("")
    prompt_parts.append("")

print("\n".join(prompt_parts))
' "$template" "${files[@]}"
}

# ── Write output for a single extraction result ──────────────────────

write_single_output() {
    # $1 = JSON string (single result object)
    # Writes to OUTPUT_DIR/{id}.json
    local json_str="$1"

    local conv_id
    conv_id=$(echo "$json_str" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])' 2>/dev/null) || return 1

    local outfile="$OUTPUT_DIR/${conv_id}.json"
    echo "$json_str" | python3 -c 'import sys,json; json.dump(json.load(sys.stdin),sys.stdout,indent=2)' > "$outfile"
    vlog "Wrote $outfile"
}

# ── Write output for a batch extraction result ───────────────────────

write_batch_output() {
    # $1 = JSON string (array of result objects)
    # Writes each element to OUTPUT_DIR/{id}.json
    # Returns the count written on stdout
    local json_str="$1"

    python3 -c '
import sys, json, os

output_dir = sys.argv[1]
results = json.loads(sys.argv[2])
if not isinstance(results, list):
    results = [results]

count = 0
for r in results:
    conv_id = r.get("id")
    if not conv_id:
        continue
    outpath = os.path.join(output_dir, f"{conv_id}.json")
    with open(outpath, "w") as f:
        json.dump(r, f, indent=2)
    count += 1

print(count)
' "$OUTPUT_DIR" "$json_str"
}

# ── Get conversation ID from a file without loading everything ────────

get_conv_id() {
    python3 -c '
import sys, json
with open(sys.argv[1]) as f:
    print(json.load(f)["id"])
' "$1" 2>/dev/null
}

# ── Print progress summary ────────────────────────────────────────────

print_progress() {
    local elapsed=$(( $(date +%s) - START_EPOCH ))
    local processed=$(( COMPLETED + FAILED + SKIPPED ))
    local remaining=$(( TOTAL - processed ))
    local rate="n/a"
    if (( elapsed > 0 && COMPLETED > 0 )); then
        rate=$(python3 -c "print(f'{$COMPLETED / ($elapsed / 60.0):.1f}')")
    fi
    log "Progress: ${processed}/${TOTAL} (done=${COMPLETED} fail=${FAILED} skip=${SKIPPED}) | remaining=${remaining} | ${elapsed}s elapsed | ${rate} conv/min"
}

# ── Argument parsing ─────────────────────────────────────────────────

while getopts "i:o:p:d:r:b:m:j:nvh" opt; do
    case "$opt" in
        i) INPUT_DIR="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
        p) PROMPT_FILE="$OPTARG" ;;
        d) DELAY="$OPTARG" ;;
        r) RPM_LIMIT="$OPTARG" ;;
        b) BATCH_SIZE="$OPTARG" ;;
        m) MODEL="$OPTARG" ;;
        j) PROGRESS_FILE="$OPTARG" ;;
        n) DRY_RUN=true ;;
        v) VERBOSE=true ;;
        h) usage ;;
        *) die "Unknown option. Use -h for help." ;;
    esac
done

# ── Validation ────────────────────────────────────────────────────────

[[ -n "$INPUT_DIR" ]]  || die "Input directory required (-i)"
[[ -n "$OUTPUT_DIR" ]] || die "Output directory required (-o)"
[[ -d "$INPUT_DIR" ]]  || die "Input directory does not exist: $INPUT_DIR"
[[ -f "$PROMPT_FILE" ]] || die "Prompt file not found: $PROMPT_FILE"

command -v claude >/dev/null 2>&1 || die "claude CLI not found on PATH"
command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"

mkdir -p "$OUTPUT_DIR"
[[ -z "$PROGRESS_FILE" ]] && PROGRESS_FILE="$OUTPUT_DIR/progress.json"

PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")

# ── Collect input files ──────────────────────────────────────────────

mapfile -t INPUT_FILES < <(find "$INPUT_DIR" -maxdepth 1 -name '*.json' -type f | sort)
TOTAL=${#INPUT_FILES[@]}

if (( TOTAL == 0 )); then
    die "No .json files found in $INPUT_DIR"
fi

log "Found $TOTAL conversation files in $INPUT_DIR"
log "Output directory: $OUTPUT_DIR"
log "Batch size: $BATCH_SIZE | Delay: ${DELAY}s | RPM limit: $RPM_LIMIT | Model: $MODEL"

# ── Filter out already-completed conversations ───────────────────────

declare -a PENDING_FILES=()
for f in "${INPUT_FILES[@]}"; do
    conv_id=$(get_conv_id "$f") || { log "WARN: could not read id from $f, skipping"; (( SKIPPED++ )) || true; continue; }
    if [[ -f "$OUTPUT_DIR/${conv_id}.json" ]]; then
        vlog "Already complete: $conv_id"
        (( SKIPPED++ )) || true
    else
        PENDING_FILES+=("$f")
    fi
done

log "${#PENDING_FILES[@]} conversations to process (${SKIPPED} already complete)"

if [[ "$DRY_RUN" == true ]]; then
    log "DRY RUN -- would process:"
    for f in "${PENDING_FILES[@]}"; do
        conv_id=$(get_conv_id "$f")
        echo "  $conv_id  ($f)"
    done
    log "Total: ${#PENDING_FILES[@]} conversations in $(( (${#PENDING_FILES[@]} + BATCH_SIZE - 1) / BATCH_SIZE )) batches"
    exit 0
fi

# ── Main processing loop ─────────────────────────────────────────────

START_EPOCH=$(date +%s)
save_progress

idx=0
pending_count=${#PENDING_FILES[@]}
progress_counter=0

while (( idx < pending_count )); do
    if [[ "$SHUTDOWN_REQUESTED" == true ]]; then
        log "Shutdown: stopping before next batch"
        break
    fi

    # Gather batch
    declare -a batch_files=()
    declare -a batch_ids=()
    local_end=$(( idx + BATCH_SIZE ))
    if (( local_end > pending_count )); then
        local_end=$pending_count
    fi

    for (( j=idx; j<local_end; j++ )); do
        batch_files+=("${PENDING_FILES[$j]}")
        batch_ids+=("$(get_conv_id "${PENDING_FILES[$j]}")")
    done
    idx=$local_end

    batch_label=$(IFS=','; echo "${batch_ids[*]}")
    vlog "Processing batch [${#batch_files[@]}]: $batch_label"

    # Rate limit
    if ! rpm_wait; then
        log "Shutdown during rate limit wait"
        break
    fi

    # Build prompt
    local_prompt=""
    if (( ${#batch_files[@]} == 1 )); then
        local_prompt=$(build_single_prompt "${batch_files[0]}" "$PROMPT_TEMPLATE")
    else
        local_prompt=$(build_batch_prompt "$PROMPT_TEMPLATE" "${batch_files[@]}")
    fi

    # Call claude
    result_json=""
    if result_json=$(call_with_backoff "$local_prompt"); then
        record_call

        if (( ${#batch_files[@]} == 1 )); then
            if write_single_output "$result_json"; then
                (( COMPLETED++ )) || true
                vlog "OK: ${batch_ids[0]}"
            else
                (( FAILED++ )) || true
                log "FAIL (write): ${batch_ids[0]}"
            fi
        else
            written=$(write_batch_output "$result_json")
            (( COMPLETED += written )) || true
            expected=${#batch_files[@]}
            if (( written < expected )); then
                missed=$(( expected - written ))
                (( FAILED += missed )) || true
                log "WARN: batch had $expected conversations but only $written were written"
            fi
            vlog "OK: batch wrote $written results"
        fi
    else
        record_call
        batch_count=${#batch_files[@]}
        (( FAILED += batch_count )) || true
        log "FAIL (all retries exhausted): $batch_label"
    fi

    # Progress reporting
    (( progress_counter += ${#batch_files[@]} )) || true
    if (( progress_counter >= 10 )); then
        print_progress
        progress_counter=0
    fi

    save_progress

    # Inter-call delay (skip if shutting down)
    if [[ "$SHUTDOWN_REQUESTED" != true ]] && (( idx < pending_count )); then
        sleep "$DELAY"
    fi
done

# ── Final summary ────────────────────────────────────────────────────

save_progress
echo ""
print_progress
log "Progress file: $PROGRESS_FILE"

if [[ "$SHUTDOWN_REQUESTED" == true ]]; then
    log "Interrupted -- run again with the same arguments to resume"
    exit 130
fi

if (( FAILED > 0 )); then
    log "Some conversations failed -- check logs above"
    exit 1
fi

log "Done"
exit 0
