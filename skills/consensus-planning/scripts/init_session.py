#!/usr/bin/env python3
"""
Initialize a consensus planning session.

Creates session.json, log.json, and proposal.json in the working directory
with stratified perspective assignments for each analyst.

Usage:
    python3 init_session.py \
        --working-dir ./planning \
        --num-analysts 5 \
        --problem "The problem statement" \
        --analysts '[{"name": "Security Analyst", "priorities": ["security"]}]'
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone


def generate_session_id():
    now = datetime.now(timezone.utc)
    return f"session-{now.strftime('%Y%m%d')}-{random.randint(100, 999)}"


def perspective_label(score):
    if score >= 75:
        return "Bold"
    elif score >= 50:
        return "Balanced"
    elif score >= 25:
        return "Critical"
    return "Conservative"


def stratified_assign(num_agents, p_min=5, p_max=95):
    """Stratified random assignment across equal bands."""
    band_size = (p_max - p_min) / num_agents
    scores = []
    for i in range(num_agents):
        lo = p_min + (i * band_size)
        hi = p_min + ((i + 1) * band_size)
        score = random.randint(int(lo), int(hi))
        scores.append(max(p_min, min(p_max, score)))
    random.shuffle(scores)
    return scores


def main():
    parser = argparse.ArgumentParser(description="Initialize a consensus planning session")
    parser.add_argument("--working-dir", required=True)
    parser.add_argument("--num-analysts", type=int, required=True)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--analysts", required=True,
                        help="JSON array of {name, priorities}")
    parser.add_argument("--focus-areas", default="[]",
                        help="JSON array of focus area strings")
    args = parser.parse_args()

    try:
        analysts = json.loads(args.analysts)
    except json.JSONDecodeError as e:
        print(f"Error parsing analysts JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if len(analysts) != args.num_analysts:
        print(f"Warning: {len(analysts)} analysts for {args.num_analysts} seats.",
              file=sys.stderr)

    try:
        focus_areas = json.loads(args.focus_areas)
    except json.JSONDecodeError:
        focus_areas = []

    os.makedirs(args.working_dir, exist_ok=True)
    session_id = generate_session_id()
    perspectives = stratified_assign(len(analysts))

    # Session state
    session = {
        "session_id": session_id,
        "problem_statement": args.problem,
        "focus_areas": focus_areas,
        "current_round": 0,
        "max_rounds": 6,
        "proposal_version": 0,
        "drafter": None,
        "status": "setup",
        "next_message_id": 1,
        "debate_clock": {
            "max_exchanges_per_round": len(analysts) * 2,
            "response_budget": 6,
            "exchanges_this_round": 0
        },
        "analysts": [],
        "assessment_history": []
    }

    for i, a in enumerate(analysts):
        session["analysts"].append({
            "agent_id": f"analyst_{i + 1}",
            "name": a["name"],
            "perspective": perspectives[i],
            "perspective_history": [{"round": 0, "perspective": perspectives[i]}],
            "priorities": a.get("priorities", []),
            "priority_satisfaction": {},
            "is_quiet": False,
            "voting_record": []
        })

    # Log
    log = {"session_id": session_id, "problem_statement": args.problem, "messages": []}

    # Proposal (empty)
    proposal = {
        "proposal_id": None, "title": None, "version": 0, "drafter": None,
        "sections": {
            "problem": "", "scope": {"in_scope": [], "out_of_scope": [], "assumptions": []},
            "solution": "", "implementation": ""
        },
        "revisions": []
    }

    # Write files
    for name, data in [("session.json", session), ("log.json", log), ("proposal.json", proposal)]:
        path = os.path.join(args.working_dir, name)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Created: {path}")

    # Print roster
    print(f"\n{'='*60}")
    print(f"Session {session_id} initialized")
    print(f"Problem: {args.problem[:80]}...")
    print(f"{'='*60}")
    print(f"\nPanel ({len(session['analysts'])} analysts):\n")

    for a in session["analysts"]:
        label = perspective_label(a["perspective"])
        print(f"  {a['name']} ({a['agent_id']})")
        print(f"    Perspective: {a['perspective']} ({label})")
        print(f"    Priorities: {', '.join(a['priorities'])}")
        print()

    print("Session is ready.")


if __name__ == "__main__":
    main()
