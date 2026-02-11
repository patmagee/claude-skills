#!/usr/bin/env python3
"""
Initialize a parliament session.

Creates the session.json, ledger.json, and bill.json files in the specified
working directory with stratified temperature assignments for each representative.

Temperatures are assigned using stratified randomness: the range is divided into
N equal bands (one per seat) and each agent gets a random temperature within a
unique band. This guarantees diversity across the full spectrum.

Usage:
    python3 init_parliament.py \
        --working-dir ./parliament \
        --num-seats 5 \
        --problem "The problem statement" \
        --representatives '[{"name": "Rep. Alpha", "motives": ["cost", "speed"]}]'
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone


def generate_parliament_id():
    """Generate a unique parliament ID."""
    now = datetime.now(timezone.utc)
    rand_suffix = random.randint(100, 999)
    return f"parl-{now.strftime('%Y%m%d')}-{rand_suffix}"


def temp_label(temp):
    """Get human-readable temperature label."""
    if temp >= 75:
        return "Visionary"
    elif temp >= 50:
        return "Pragmatic Advocate"
    elif temp >= 25:
        return "Rigorous Skeptic"
    else:
        return "Principled Guardian"


def stratified_assign(num_agents, temp_min=5, temp_max=95):
    """
    Assign temperatures using stratified randomness.

    Divides [temp_min, temp_max] into num_agents equal bands,
    assigns one random temperature per band, then shuffles.
    """
    total_range = temp_max - temp_min
    band_size = total_range / num_agents

    temperatures = []
    for i in range(num_agents):
        band_start = temp_min + (i * band_size)
        band_end = temp_min + ((i + 1) * band_size)
        temp = random.randint(int(band_start), int(band_end))
        temp = max(temp_min, min(temp_max, temp))
        temperatures.append(temp)

    random.shuffle(temperatures)
    return temperatures


def create_session(parliament_id, problem, representatives, constituent_issues=None):
    """Create the session state object."""
    temperatures = stratified_assign(len(representatives))

    session = {
        "parliament_id": parliament_id,
        "problem_statement": problem,
        "constituent_issues": constituent_issues or [],
        "current_round": 0,
        "max_rounds": 6,
        "bill_version": 0,
        "drafter": None,
        "status": "setup",
        "next_message_id": 1,
        "debate_clock": {
            "max_exchanges_per_round": len(representatives) * 2,
            "response_budget": 6,
            "exchanges_this_round": 0
        },
        "representatives": []
    }

    for i, rep in enumerate(representatives):
        agent_id = f"rep_{i + 1}"
        session["representatives"].append({
            "agent_id": agent_id,
            "name": rep["name"],
            "temperature": temperatures[i],
            "temperature_history": [
                {"round": 0, "temperature": temperatures[i]}
            ],
            "motives": rep.get("motives", []),
            "is_quiet": False,
            "quiet_until_round": None,
            "voting_record": []
        })

    session["vote_history"] = []
    return session


def create_ledger(parliament_id, problem):
    """Create an empty ledger."""
    return {
        "parliament_id": parliament_id,
        "problem_statement": problem,
        "messages": []
    }


def create_bill():
    """Create an empty bill."""
    return {
        "bill_id": None,
        "title": None,
        "version": 0,
        "drafter": None,
        "sections": {
            "problem": "",
            "scope": {
                "in_scope": [],
                "out_of_scope": [],
                "assumptions": [],
                "definitions": []
            },
            "solution": "",
            "implementation": ""
        },
        "amendments": []
    }


def main():
    parser = argparse.ArgumentParser(description="Initialize a parliament session")
    parser.add_argument("--working-dir", required=True, help="Directory for session files")
    parser.add_argument("--num-seats", type=int, required=True, help="Number of seats")
    parser.add_argument("--problem", required=True, help="Problem statement")
    parser.add_argument("--representatives", required=True,
                        help="JSON array of {name, motives} objects")
    parser.add_argument("--issues", default="[]",
                        help="JSON array of constituent issue strings")

    args = parser.parse_args()

    # Parse representatives
    try:
        representatives = json.loads(args.representatives)
    except json.JSONDecodeError as e:
        print(f"Error parsing representatives JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if len(representatives) != args.num_seats:
        print(f"Warning: {len(representatives)} representatives provided for "
              f"{args.num_seats} seats. Using {len(representatives)} representatives.",
              file=sys.stderr)

    # Parse issues
    try:
        issues = json.loads(args.issues)
    except json.JSONDecodeError:
        issues = []

    # Create working directory
    os.makedirs(args.working_dir, exist_ok=True)

    # Generate parliament ID
    parliament_id = generate_parliament_id()

    # Create files
    session = create_session(parliament_id, args.problem, representatives, issues)
    ledger = create_ledger(parliament_id, args.problem)
    bill = create_bill()

    # Write files
    session_path = os.path.join(args.working_dir, "session.json")
    ledger_path = os.path.join(args.working_dir, "ledger.json")
    bill_path = os.path.join(args.working_dir, "bill.json")

    with open(session_path, "w") as f:
        json.dump(session, f, indent=2)
    print(f"Created: {session_path}")

    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2)
    print(f"Created: {ledger_path}")

    with open(bill_path, "w") as f:
        json.dump(bill, f, indent=2)
    print(f"Created: {bill_path}")

    # Print roster
    print(f"\n{'='*60}")
    print(f"Parliament {parliament_id} initialized")
    print(f"Problem: {args.problem[:80]}...")
    print(f"Assignment: stratified across {len(session['representatives'])} bands")
    print(f"{'='*60}")
    print(f"\nRoster ({len(session['representatives'])} seats):\n")

    for rep in session["representatives"]:
        temp = rep["temperature"]
        label = temp_label(temp)

        print(f"  {rep['name']} ({rep['agent_id']})")
        print(f"    Temperature: {temp} ({label})")
        print(f"    Motives: {', '.join(rep['motives'])}")
        print()

    print("Parliament is ready for session.")
    return session


if __name__ == "__main__":
    main()
