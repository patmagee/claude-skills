#!/usr/bin/env python3
"""
Reassign analyst perspectives with stratified randomness and convergence.

As rounds progress, the perspective range narrows toward center, creating
natural pressure toward consensus.

Usage:
    python3 reassign_perspectives.py --session-file ./planning/session.json
"""

import argparse
import json
import random
import sys

CONVERGENCE_TABLE = {
    0: (5, 95), 1: (5, 95), 2: (10, 90), 3: (15, 85),
    4: (25, 75), 5: (30, 70), 6: (35, 65),
}

DEBATE_CLOCK_TABLE = {
    0: (2.0, 6), 1: (2.0, 6), 2: (2.0, 5), 3: (1.5, 4),
    4: (1.5, 3), 5: (1.0, 3), 6: (1.0, 2),
}


def perspective_label(score):
    if score >= 75:
        return "Bold"
    elif score >= 50:
        return "Balanced"
    elif score >= 25:
        return "Critical"
    return "Conservative"


def stratified_assign(num_agents, p_min, p_max):
    band_size = (p_max - p_min) / num_agents
    scores = []
    for i in range(num_agents):
        lo = p_min + (i * band_size)
        hi = p_min + ((i + 1) * band_size)
        scores.append(max(p_min, min(p_max, random.randint(int(lo), int(hi)))))
    random.shuffle(scores)
    return scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-file", required=True)
    args = parser.parse_args()

    try:
        with open(args.session_file, "r") as f:
            session = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    next_round = session.get("current_round", 0) + 1
    p_min, p_max = CONVERGENCE_TABLE.get(next_round, (35, 65))
    num = len(session["analysts"])

    mult, budget = DEBATE_CLOCK_TABLE.get(next_round, (1.0, 2))
    max_exchanges = int(num * mult)
    session["debate_clock"] = {
        "max_exchanges_per_round": max_exchanges,
        "response_budget": budget,
        "exchanges_this_round": 0
    }

    print(f"Round {next_round} | Range: {p_min}-{p_max} | "
          f"Clock: {max_exchanges} exchanges, {budget} sentences")
    print(f"{'='*60}\n")

    new_scores = stratified_assign(num, p_min, p_max)

    for i, a in enumerate(session["analysts"]):
        old = a["perspective"]
        new = new_scores[i]
        a.setdefault("perspective_history", []).append(
            {"round": next_round, "perspective": new})
        a["perspective"] = new

        shift = ""
        diff = abs(new - old)
        if diff > 30:
            shift = " *** BIG SHIFT ***"
        elif diff > 15:
            shift = " (notable shift)"

        print(f"  {a['name']}: {old} ({perspective_label(old)}) -> "
              f"{new} ({perspective_label(new)}){shift}")

    session["current_round"] = next_round

    with open(args.session_file, "w") as f:
        json.dump(session, f, indent=2)
    print(f"\nUpdated: {args.session_file}")


if __name__ == "__main__":
    main()
