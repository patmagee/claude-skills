#!/usr/bin/env python3
"""
Append a message to the parliament ledger.

Reads the current ledger, appends the message with proper metadata
(id, round, timestamp), increments the session's next_message_id counter,
and writes both files back.

This avoids the orchestrator needing to read the full ledger into its
context window just to append a single message.

Usage:
    python3 append_to_ledger.py \
        --working-dir ./parliament \
        --message '{"type": "QUESTION", "from": "rep_1", ...}'

    # Append multiple messages at once (e.g., parallel opening statements):
    python3 append_to_ledger.py \
        --working-dir ./parliament \
        --message '[{"type": "OPENING_STATEMENT", ...}, ...]'
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description="Append message(s) to the ledger")
    parser.add_argument("--working-dir", required=True, help="Parliament working directory")
    parser.add_argument("--message", required=True,
                        help="JSON message object or array of message objects (without id/round/timestamp)")
    args = parser.parse_args()

    session_path = f"{args.working_dir}/session.json"
    ledger_path = f"{args.working_dir}/ledger.json"

    # Read session state
    try:
        with open(session_path, "r") as f:
            session = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading session: {e}", file=sys.stderr)
        sys.exit(1)

    # Read ledger
    try:
        with open(ledger_path, "r") as f:
            ledger = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading ledger: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse message(s)
    try:
        raw = json.loads(args.message)
    except json.JSONDecodeError as e:
        print(f"Error parsing message JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Normalize to list
    messages = raw if isinstance(raw, list) else [raw]

    current_round = session.get("current_round", 0)
    next_id = session.get("next_message_id", 1)
    now = datetime.now(timezone.utc).isoformat()

    appended = []
    for msg in messages:
        msg["id"] = f"msg-{next_id:03d}"
        msg["round"] = current_round
        msg["timestamp"] = now
        ledger["messages"].append(msg)
        appended.append({"id": msg["id"], "type": msg.get("type", "unknown")})
        next_id += 1

    # Update session counter
    session["next_message_id"] = next_id

    # Write both files
    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2)

    with open(session_path, "w") as f:
        json.dump(session, f, indent=2)

    # Output summary (minimal — orchestrator only needs IDs)
    for entry in appended:
        print(f"Appended {entry['id']} ({entry['type']})")


if __name__ == "__main__":
    main()
