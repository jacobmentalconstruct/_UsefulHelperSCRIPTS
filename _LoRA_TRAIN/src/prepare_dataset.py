# _training/prepare_dataset.py
# Converts Mind-Shard session/memory logs into ShareGPT JSONL for Unsloth training.
#
# Sources it reads:
#   _logs/memory/memory_log.json  — NDJSON (one JSON object per line)
#   _logs/sessions/*.json         — each has a "history" list
#
# Output:
#   _training/data/train.jsonl    — one ShareGPT conversation per line

import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT_DIR / "_logs"
MEMORY_LOG = LOGS_DIR / "memory" / "memory_log.json"
SESSIONS_DIR = LOGS_DIR / "sessions"
OUTPUT_FILE = Path(__file__).resolve().parent / "data" / "train.jsonl"


def load_memory_log():
    """Read the NDJSON memory log into a list of message dicts."""
    if not MEMORY_LOG.exists():
        return []
    messages = []
    with open(MEMORY_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return messages


def load_session_files():
    """Read all saved session JSON files, return their history lists."""
    histories = []
    if not SESSIONS_DIR.exists():
        return histories
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if "history" in data and isinstance(data["history"], list):
                histories.append(data["history"])
        except (json.JSONDecodeError, KeyError):
            continue
    return histories


def messages_to_sharegpt(messages):
    """
    Convert a flat list of {role, content} messages into ShareGPT conversations.

    Rules:
    - Skip system messages (injected summaries, not real dialogue).
    - Group consecutive user→assistant pairs into conversations.
    - A new conversation starts when a second user turn appears after an assistant turn.
    """
    conversations = []
    current = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()

        if role == "system" or not content:
            # Flush current conversation on system boundary
            if current:
                conversations.append({"conversations": current})
                current = []
            continue

        if role == "user":
            if current and current[-1]["from"] == "gpt":
                # Previous turn was assistant — start a new conversation
                conversations.append({"conversations": current})
                current = []
            current.append({"from": "human", "value": content})

        elif role == "assistant":
            if current and current[-1]["from"] == "human":
                current.append({"from": "gpt", "value": content})

    if current:
        conversations.append({"conversations": current})

    return conversations


def is_valid(conv):
    """Keep only conversations that have at least one human+gpt pair."""
    turns = conv.get("conversations", [])
    has_human = any(t["from"] == "human" for t in turns)
    has_gpt = any(t["from"] == "gpt" for t in turns)
    return has_human and has_gpt


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    all_conversations = []

    # --- Memory log ---
    memory_messages = load_memory_log()
    if memory_messages:
        convs = messages_to_sharegpt(memory_messages)
        all_conversations.extend(convs)
        print(f"Memory log: {len(convs)} conversation(s) extracted.")
    else:
        print("Memory log: not found or empty.")

    # --- Session files ---
    session_histories = load_session_files()
    session_conv_count = 0
    for history in session_histories:
        convs = messages_to_sharegpt(history)
        all_conversations.extend(convs)
        session_conv_count += len(convs)
    print(f"Session files: {len(session_histories)} file(s), {session_conv_count} conversation(s) extracted.")

    # --- Filter and deduplicate ---
    valid = [c for c in all_conversations if is_valid(c)]
    total_turns = sum(
        len([t for t in c["conversations"] if t["from"] == "human"])
        for c in valid
    )

    print(f"\nTotal valid conversations: {len(valid)}")
    print(f"Total user turns (training examples): {total_turns}")

    if total_turns < 100:
        print(
            "\n⚠️  Warning: fewer than 100 turns found. Fine-tuning on this little data "
            "will likely overfit. Add more sources (Discord exports, emails, transcripts) "
            "before training."
        )

    # --- Write output ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for conv in valid:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")

    print(f"\n✅ Dataset written to: {OUTPUT_FILE}")
    print("   Inspect a few lines before training to confirm the format looks right.")


if __name__ == "__main__":
    main()
