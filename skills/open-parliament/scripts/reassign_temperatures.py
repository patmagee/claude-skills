#!/usr/bin/env python3
"""
Reassign temperatures using stratified randomness and convergence pressure.

Stratified: divides the temperature range into N equal bands (one per seat)
and randomly assigns one agent to each band. This guarantees diversity.

Convergence: as rounds progress, the temperature range narrows toward the
center, creating natural pressure toward consensus in later rounds.

Usage:
    python3 reassign_temperatures.py --session-file ./parliament/session.json
"""

import argparse
import json
import random
import sys


# Convergence table: round -> (min_temp, max_temp)
CONVERGENCE_TABLE = {
    0: (5, 95),    # Drafting round — full spectrum
    1: (5, 95),    # Round 1 — full spectrum, max creative tension
    2: (10, 90),   # Round 2 — still wide
    3: (15, 85),   # Round 3 — noticeable convergence
    4: (25, 75),   # Round 4 — deal-making mode
    5: (30, 70),   # Round 5 — focused on finalizing
    6: (35, 65),   # Round 6 — max compromise pressure
}


def get_range_for_round(round_num):
    """Get the temperature range for a given round, with convergence."""
    if round_num in CONVERGENCE_TABLE:
        return CONVERGENCE_TABLE[round_num]
    # Beyond round 6 (e.g., post-veto rounds), use tightest range
    return (35, 65)


# Debate clock table: round -> (exchange_multiplier, response_budget_sentences)
DEBATE_CLOCK_TABLE = {
    0: (2.0, 6),
    1: (2.0, 6),
    2: (2.0, 5),
    3: (1.5, 4),
    4: (1.5, 3),
    5: (1.0, 3),
    6: (1.0, 2),
}


def get_debate_clock(round_num, num_agents):
    """Get debate clock settings for a given round."""
    if round_num in DEBATE_CLOCK_TABLE:
        multiplier, budget = DEBATE_CLOCK_TABLE[round_num]
    else:
        multiplier, budget = (1.0, 2)
    max_exchanges = int(num_agents * multiplier)
    return max_exchanges, budget


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


def stratified_assign(num_agents, temp_min, temp_max):
    """
    Assign temperatures using stratified randomness.

    Divides [temp_min, temp_max] into num_agents equal bands,
    assigns one random temperature per band, then shuffles the
    assignments so agents don't always get the same relative position.
    """
    total_range = temp_max - temp_min
    band_size = total_range / num_agents

    temperatures = []
    for i in range(num_agents):
        band_start = temp_min + (i * band_size)
        band_end = temp_min + ((i + 1) * band_size)
        # Random temperature within this band
        temp = random.randint(int(band_start), int(band_end))
        # Clamp to valid range
        temp = max(temp_min, min(temp_max, temp))
        temperatures.append(temp)

    # Shuffle so band position isn't correlated with agent order
    random.shuffle(temperatures)
    return temperatures


def main():
    parser = argparse.ArgumentParser(description="Reassign temperatures (stratified + convergence)")
    parser.add_argument("--session-file", required=True, help="Path to session.json")
    args = parser.parse_args()

    # Read session
    try:
        with open(args.session_file, "r") as f:
            session = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading session file: {e}", file=sys.stderr)
        sys.exit(1)

    current_round = session.get("current_round", 0)
    next_round = current_round + 1
    temp_min, temp_max = get_range_for_round(next_round)
    num_agents = len(session["representatives"])

    # Update debate clock
    max_exchanges, response_budget = get_debate_clock(next_round, num_agents)
    session["debate_clock"] = {
        "max_exchanges_per_round": max_exchanges,
        "response_budget": response_budget,
        "exchanges_this_round": 0
    }

    print(f"Reassigning temperatures for Round {next_round}")
    print(f"Range: {temp_min} - {temp_max} (convergence pressure)")
    print(f"Assignment: stratified across {num_agents} bands")
    print(f"Debate clock: {max_exchanges} exchanges, {response_budget} sentences/response")
    print(f"{'='*60}\n")

    # Generate stratified temperatures
    new_temps = stratified_assign(num_agents, temp_min, temp_max)

    # Apply and display
    for i, rep in enumerate(session["representatives"]):
        old_temp = rep["temperature"]
        new_temp = new_temps[i]
        rep["temperature"] = new_temp

        old_label = temp_label(old_temp)
        new_label = temp_label(new_temp)

        shift_note = ""
        diff = abs(new_temp - old_temp)
        if diff > 30:
            shift_note = " *** BIG SHIFT ***"
        elif diff > 15:
            shift_note = " (notable shift)"

        print(f"  {rep['name']}:")
        print(f"    {old_temp} ({old_label}) -> {new_temp} ({new_label}){shift_note}")
        print()

    # Advance the round counter
    session["current_round"] = next_round

    # Write back
    with open(args.session_file, "w") as f:
        json.dump(session, f, indent=2)

    print(f"Updated: {args.session_file}")


if __name__ == "__main__":
    main()
