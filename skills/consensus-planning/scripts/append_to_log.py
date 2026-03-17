#!/usr/bin/env python3
"""
Append message(s) to the session log.

Reads log.json, appends with metadata (id, round, timestamp), increments
next_message_id in session.json, writes both back.

Usage:
    python3 append_to_log.py \
        --working-dir ./planning \
        --message '{"type": "CRITIQUE", "from": "analyst_1", ...}'

    # Multiple messages:
    python3 append_to_log.py \
        --working-dir ./planning \
        --message '[{"type": "INITIAL_ANALYSIS", ...}, ...]'
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--working-dir", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    session_path = f"{args.working_dir}/session.json"
    log_path = f"{args.working_dir}/log.json"

    try:
        with open(session_path) as f:
            session = json.load(f)
        with open(log_path) as f:
            log = json.load(f)
        raw = json.loads(args.message)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    messages = raw if isinstance(raw, list) else [raw]
    current_round = session.get("current_round", 0)
    next_id = session.get("next_message_id", 1)
    now = datetime.now(timezone.utc).isoformat()

    for msg in messages:
        msg["id"] = f"msg-{next_id:03d}"
        msg["round"] = current_round
        msg["timestamp"] = now
        log["messages"].append(msg)
        print(f"Appended {msg['id']} ({msg.get('type', 'unknown')})")
        next_id += 1

    session["next_message_id"] = next_id

    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)
    with open(session_path, "w") as f:
        json.dump(session, f, indent=2)


if __name__ == "__main__":
    main()
